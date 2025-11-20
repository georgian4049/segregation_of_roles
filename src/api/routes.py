"""API route definitions."""
import logging
import tempfile
import shutil
import io
import csv
from typing import Annotated, List, Dict
from pathlib import Path
from copy import deepcopy
import asyncio
import json

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.responses import (
    StreamingResponse,
)

from src.schemas import (
    IngestResponse,
    DecisionRequest,
    FindingResponse,
    EvidenceLog,
    SimulationRequest,
    SimulationResponse,
)
from src.models import UserViolationProfile
from src.services.ingestion import CSVValidationError, IngestionService
from src.services.detection import DetectionEngine
from src.services.llm_service import get_llm_service
from src.services.policy_store import PolicyStore

logger = logging.getLogger(__name__)

router = APIRouter()
ingestion_service = IngestionService()
policy_store = PolicyStore()
llm_service = get_llm_service()

_decisions_store: List[DecisionRequest] = []
_findings_cache: Dict[str, FindingResponse] = {}


def _validate_csv_upload(upload: UploadFile, label: str) -> None:
    filename = upload.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail=f"{label} must be a .csv file.",
        )


@router.post("/ingest", response_model=IngestResponse)
async def ingest_data(
    assignments: Annotated[UploadFile, File(description="Assignments CSV file")],
    policies: Annotated[
        UploadFile | None, File(description="Policies CSV (optional)")
    ] = None,
) -> IngestResponse:
    safe_assignments_filename = "".join(
        c
        for c in (assignments.filename or "unknown")
        if c.isalnum() or c in (".", "_", "-")
    ).strip()
    logger.info(f"Ingesting assignments from {safe_assignments_filename}")
    _validate_csv_upload(assignments, "Assignments upload")

    assignments_path: Path | None = None
    policies_path: Path | None = None
    tmp_assignments_file = None
    tmp_policies_file = None

    try:
        tmp_assignments_file = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        with tmp_assignments_file as f:
            shutil.copyfileobj(assignments.file, f)
        assignments_path = Path(tmp_assignments_file.name)

        if policies:
            safe_policies_filename = "".join(
                c
                for c in (policies.filename or "unknown")
                if c.isalnum() or c in (".", "_", "-")
            ).strip()
            logger.info(f"Ingesting policies from {safe_policies_filename}")
            _validate_csv_upload(policies, "Policies upload")
            tmp_policies_file = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
            with tmp_policies_file as f:
                shutil.copyfileobj(policies.file, f)
            policies_path = Path(tmp_policies_file.name)

        response = ingestion_service.process_ingestion(assignments_path, policies_path)
        policy_store.update_policies(ingestion_service.get_all_policies())

        logger.info(f"Ingestion successful: {response.model_dump()}")
        return response

    except CSVValidationError as e:
        logger.error(f"CSV validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    finally:
        if assignments:
            assignments.file.close()
        if tmp_assignments_file and Path(tmp_assignments_file.name).exists():
            Path(tmp_assignments_file.name).unlink()
        if policies:
            policies.file.close()
        if tmp_policies_file and Path(tmp_policies_file.name).exists():
            Path(tmp_policies_file.name).unlink()


async def stream_findings(violation_profiles: dict[str, UserViolationProfile]):
    """
    Async generator to process and stream findings one by one.
    """
    global _findings_cache, _decisions_store

    profiles_to_process = list(violation_profiles.values())

    logger.info(f"Streaming {len(profiles_to_process)} findings...")

    for profile in profiles_to_process:
        try:
            justification = await llm_service.generate_user_remediation(profile)

            response = FindingResponse(profile=profile, justification=justification)

            _findings_cache[profile.user.user_id] = response

            yield f"data: {response.model_dump_json()}\n\n"

            await asyncio.sleep(
                0.01
            )  # Just for the purpose to give user a feeling of streaming

        except Exception as e:
            logger.error(
                f"Failed to stream finding for {profile.user.user_id}: {e}",
                exc_info=True,
            )

            error_payload = {
                "error": True,
                "user_id": profile.user.user_id,
                "message": str(e),
            }
            yield f"data: {json.dumps(error_payload)}\n\n"

    try:
        logger.info("Stream complete. Sending done event.")
        yield 'event: done\ndata: {"message": "Stream complete"}\n\n'
    except Exception as e:
        logger.warning(f"Failed to send 'done' event: {e}")


@router.get("/findings")
async def get_findings():
    global _findings_cache, _decisions_store
    user_states = ingestion_service.get_all_user_states()

    if not user_states and not ingestion_service.last_ingest:
        raise HTTPException(
            status_code=400,
            detail="No data ingested or no users with violations. Call /ingest first.",
        )

    try:
        _findings_cache = {}
        _decisions_store = []
        logger.info(f"Generating new findings for {len(user_states)} users.")

        detection_engine = DetectionEngine(policy_store)
        violation_profiles = detection_engine.detect_violations(user_states)

        if not violation_profiles:
            logger.info("No violations found.")

            # Return an empty stream
            async def empty_generator():
                yield "data: {}\n\n"

            return StreamingResponse(empty_generator(), media_type="text/event-stream")

        return StreamingResponse(
            stream_findings(violation_profiles), media_type="text/event-stream"
        )
    except Exception as e:
        logger.error(f"Detection failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Detection failed: {str(e)}")


@router.post("/decisions")
async def submit_decision(decision: DecisionRequest):
    global _findings_cache, _decisions_store
    try:
        if decision.user_id not in _findings_cache:
            raise HTTPException(
                status_code=404,
                detail=f"User {decision.user_id} not found in the current scan.",
            )

        _decisions_store = [
            d for d in _decisions_store if d.user_id != decision.user_id
        ]
        _decisions_store.append(decision)

        logger.info(
            f"Decision recorded for user {decision.user_id}: {decision.decision}"
        )
        return {
            "status": "success",
            "message": "Decision recorded",
            "decision": decision.model_dump(),
            "total_decisions": len(_decisions_store),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Decision submission failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Decision submission failed: {str(e)}"
        )


@router.get("/evidence")
async def get_evidence():
    """
    Returns the complete evidence log required for audit — includes:
    - ingestion summary
    - policies used and their hash
    - redacted findings with model prompts and outputs
    - decision records
    - metadata about the LLM provider
    """
    global _findings_cache, _decisions_store

    if not ingestion_service.last_ingest:
        raise HTTPException(
            status_code=400, detail="No data ingested. Call /ingest first."
        )
    if not _findings_cache:
        raise HTTPException(
            status_code=400, detail="No findings generated. Call /findings first."
        )

    try:
        policies = ingestion_service.get_all_policies()
        policies_hash = ingestion_service.get_policies_hash()

        redacted_findings = []
        for finding_resp in _findings_cache.values():
            finding_copy = deepcopy(finding_resp)
            user_profile = finding_copy.profile.user

            user_profile.name = "REDACTED"
            user_profile.email = llm_service._redact_email(user_profile.email)
            user_profile.user_id = None

            redacted_findings.append(finding_copy)

        evidence = EvidenceLog(
            ingestion_summary=ingestion_service.last_ingest,
            policies_used=policies,
            policies_hash=policies_hash,
            findings=redacted_findings,
            decisions=_decisions_store,
            metadata={
                "llm_provider": llm_service.provider.get_model_identifier(),
                "llm_status": llm_service.get_status(),
                "total_users": ingestion_service.last_ingest.users_processed,
                "total_findings": len(redacted_findings),
                "total_decisions": len(_decisions_store),
            },
        )

        logger.info("Evidence log generated successfully with redaction")
        return JSONResponse(
            content=json.loads(evidence.model_dump_json()), status_code=200
        )

    except Exception as e:
        logger.error(f"Evidence generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Evidence generation failed: {str(e)}"
        )


## Good to have routes
@router.post("/simulate", response_model=SimulationResponse)
async def simulate_role_change(payload: SimulationRequest) -> SimulationResponse:
    """
    Run a what-if simulation by removing a role from a user.
    This is the simple, no-LLM version.
    """
    if not ingestion_service.last_ingest:
        raise HTTPException(status_code=400, detail="No data ingested.")

    # 1. Get the *original* full user state from the service
    user_state = ingestion_service.get_full_user_state(payload.user_id)

    if not user_state:
        raise HTTPException(status_code=404, detail=f"User {payload.user_id} not found")

    if payload.role_to_remove not in user_state.active_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Role {payload.role_to_remove} not active for user {payload.user_id}",
        )

    try:
        detection_engine = DetectionEngine(policy_store)

        simulated_user_state = deepcopy(user_state)

        if payload.role_to_remove in simulated_user_state.active_roles:
            del simulated_user_state.active_roles[payload.role_to_remove]

        simulated_user_states_dict = {payload.user_id: simulated_user_state}

        # 4. Run detection *only* on the simulated user
        violations_profile = detection_engine.detect_violations(
            simulated_user_states_dict
        )

        remaining_violations: List[str] = []
        if payload.user_id in violations_profile:
            # Get the list of policy IDs that are still violated
            remaining_violations = [
                p.policy_id
                for p in violations_profile[payload.user_id].violated_policies
            ]

        # 5. Build the simple response
        resolved = len(remaining_violations) == 0
        message = (
            f"✓ All violations for this user would be resolved by removing {payload.role_to_remove}."
            if resolved
            else f"After removing {payload.role_to_remove}, {len(remaining_violations)} violation(s) would remain."
        )

        return SimulationResponse(
            user_id=payload.user_id,
            role_removed=payload.role_to_remove,
            resolved=resolved,
            violations_remaining=remaining_violations,
            message=message,
        )

    except Exception as e:
        logger.error(f"Simulation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Simulation failed: {str(e)}")


# --- Error Reporting Routes ---
@router.get("/ingest/errors/assignments")
async def get_assignment_errors():
    if not ingestion_service.assignment_errors:
        return {"message": "No assignment ingestion errors found."}
    output = io.StringIO()
    try:
        sample_data = ingestion_service.assignment_errors[0]["data"]
        headers = ["line", "error"] + list(sample_data.keys())
    except (IndexError, AttributeError):
        headers = ["line", "error", "data"]

    writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for err in ingestion_service.assignment_errors:
        row_data = err.get("data", {})
        row_data["line"] = err.get("line")
        row_data["error"] = err.get("error")
        writer.writerow(row_data)

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=assignment_errors.csv"},
    )


@router.get("/ingest/errors/policies")
async def get_policy_errors():
    if not ingestion_service.policy_errors:
        return {"message": "No policy ingestion errors found."}

    output = io.StringIO()
    headers = ["line", "error", "data"]
    writer = csv.writer(output)
    writer.writerow(headers)
    for err in ingestion_service.policy_errors:
        writer.writerow([err.get("line"), err.get("error"), str(err.get("data", ""))])

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=policy_errors.csv"},
    )
