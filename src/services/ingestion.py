"""
Core ingestion service for processing CSV files.
Implements the 'status=inactive' means user is inactive logic.
"""
import logging
import csv
import re
import json
import hashlib
from pathlib import Path
from typing import Any, List, Dict
from pydantic import ValidationError

from src.config import settings
from src.models import AssignmentStatus, ToxicPolicy, UserRoleState, RoleAssignment
from src.schemas import AssignmentRow, IngestResponse

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Base exception for ingestion errors."""

    pass


class CSVValidationError(IngestionError):
    """CSV validation failed."""

    pass


class IngestionService:
    """
    Manages the ingestion and processing of assignment and policy CSVs.
    """

    def __init__(self):
        self.user_states: Dict[str, UserRoleState] = {}
        self.all_user_states: Dict[str, UserRoleState] = {}
        self.policies: List[ToxicPolicy] = []
        self.policies_hash: str = ""
        self.last_ingest: IngestResponse | None = None
        self.assignment_errors: List[dict[str, Any]] = []
        self.policy_errors: List[dict[str, Any]] = []

    def _sanitize_for_llm(self, text: str | None) -> str | None:
        if text is None:
            return None
        text = str(text).replace("\n", " ").replace("\r", " ")
        text = text.replace("<", "").replace(">", "")
        text = text.replace("{", "").replace("}", "")
        text = text.replace("[", "").replace("]", "")
        text = text.replace("|", "")
        return text.strip()

    def _ingest_assignments(self, file: Path) -> dict:
        stats = {
            "total_assignment_rows": 0,
            "valid_assignment_rows": 0,
            "corrupt_assignment_rows": 0,
            "total_users_found": 0,
            "inactive_users_found": 0,
        }

        user_builder: dict[str, dict] = {}

        required_cols = {
            "user_id",
            "name",
            "email",
            "department",
            "status",
            "role",
            "source_system",
            "granted_at_iso",
        }

        try:
            with open(file, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                missing_cols = required_cols - set(reader.fieldnames or [])
                if missing_cols:
                    raise CSVValidationError(
                        f"Missing required columns: {missing_cols}"
                    )

                for line_number, row in enumerate(reader, start=2):
                    stats["total_assignment_rows"] += 1
                    try:
                        assignment_row = AssignmentRow(**row)
                        user_id = assignment_row.user_id

                        if user_id not in user_builder:
                            user_builder[user_id] = {
                                "user_id": user_id,
                                "name": self._sanitize_for_llm(assignment_row.name),
                                "email": assignment_row.email,
                                "department": self._sanitize_for_llm(
                                    assignment_row.department
                                ),
                                "status": AssignmentStatus.ACTIVE,
                                "active_roles": {},
                                "source_systems": set(),
                                "latest_timestamp": assignment_row.granted_at_iso,
                            }

                        if assignment_row.status == AssignmentStatus.INACTIVE:
                            user_builder[user_id]["status"] = AssignmentStatus.INACTIVE

                        sanitized_role = self._sanitize_for_llm(assignment_row.role)
                        if sanitized_role:
                            role_obj = RoleAssignment(
                                role=sanitized_role,
                                source_system=assignment_row.source_system,
                                granted_at=assignment_row.granted_at_iso,
                            )
                            user_builder[user_id]["active_roles"][
                                sanitized_role
                            ] = role_obj

                        user_builder[user_id]["source_systems"].add(
                            assignment_row.source_system
                        )

                        if (
                            assignment_row.granted_at_iso
                            > user_builder[user_id]["latest_timestamp"]
                        ):
                            user_builder[user_id][
                                "latest_timestamp"
                            ] = assignment_row.granted_at_iso
                            user_builder[user_id]["name"] = self._sanitize_for_llm(
                                assignment_row.name
                            )
                            user_builder[user_id]["email"] = assignment_row.email
                            user_builder[user_id][
                                "department"
                            ] = self._sanitize_for_llm(assignment_row.department)

                        stats["valid_assignment_rows"] += 1

                    except (ValidationError, ValueError) as e:
                        stats["corrupt_assignment_rows"] += 1
                        self.assignment_errors.append(
                            {"line": line_number, "error": str(e), "data": row}
                        )

            self.user_states = {}
            self.all_user_states = {}
            stats["total_users_found"] = len(user_builder)

            for user_id, data in user_builder.items():
                user_state_obj = UserRoleState(
                    user_id=data["user_id"],
                    name=data["name"],
                    email=data["email"],
                    department=data["department"],
                    status=data["status"],
                    active_roles=data["active_roles"],
                    source_systems=list(data["source_systems"]),
                )

                self.all_user_states[user_id] = user_state_obj

                if data["status"] == AssignmentStatus.ACTIVE:
                    if len(user_state_obj.active_roles) > 1:
                        self.user_states[user_id] = user_state_obj
                else:
                    stats["inactive_users_found"] += 1

            return stats

        except FileNotFoundError:
            raise CSVValidationError("Ingestion file not found (assignments).")
        except Exception as e:
            if isinstance(e, CSVValidationError):
                raise
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise CSVValidationError(f"Unexpected error: {e}")

    def _ingest_policies(self, file: Path) -> dict:
        stats = {
            "total_policy_rows": 0,
            "valid_policies": 0,
            "corrupt_policies": 0,
            "filtered_policies_single_role": 0,
        }
        ROLE_EXTRACTOR = re.compile(r"([A-Za-z0-9_]+)")
        required_cols = {"policy_id", "description", "roles"}

        try:
            with open(file, mode="r", encoding="utf-8") as f:
                try:
                    header_line = f.readline()
                    line_number = 1

                    header_cols = [c.strip() for c in header_line.split(",")]
                    missing_cols = required_cols - set(header_cols)

                    if missing_cols:
                        raise CSVValidationError(
                            f"Policies file missing required columns: {missing_cols}"
                        )

                except StopIteration:
                    raise CSVValidationError("Policies CSV file is empty")

                for line in f:
                    line_number += 1

                    line = line.strip()

                    if not line:
                        continue

                    # Now increment the counter for actual data attempts
                    stats["total_policy_rows"] += 1

                    try:
                        try:
                            parts = line.split(",", 2)
                            policy_id = parts[0].strip()
                            description = self._sanitize_for_llm(parts[1].strip())
                            roles_raw_string = parts[2].strip()
                        except IndexError:
                            raise ValueError(
                                "Row must have 3 parts (policy_id, description, roles)."
                            )

                        roles_list = ROLE_EXTRACTOR.findall(roles_raw_string)

                        if not roles_list:
                            raise ValueError(
                                f"Could not extract any roles from: {roles_raw_string}"
                            )
                        if len(roles_list) < 2:
                            stats["filtered_policies_single_role"] += 1
                            self.policy_errors.append(
                                {
                                    "line": line_number,
                                    "error": "Policy filtered: Must contain at least two roles.",
                                    "data": line,
                                }
                            )
                            continue

                        policy = ToxicPolicy(
                            policy_id=policy_id,
                            description=description,
                            roles=set(roles_list),
                        )
                        self.policies.append(policy)
                        stats["valid_policies"] += 1
                    except (ValidationError, ValueError, IndexError) as e:
                        stats["corrupt_policies"] += 1
                        self.policy_errors.append(
                            {
                                "line": line_number,
                                "error": str(e),
                                "data": line,
                            }
                        )

            self._update_policies_hash()
            logger.info(f"Parsed {stats['valid_policies']} valid policies.")
            if (
                stats["corrupt_policies"] > 0
                or stats["filtered_policies_single_role"] > 0
            ):
                logger.warning(
                    f"Ignored {stats['corrupt_policies']} corrupt rows and {stats['filtered_policies_single_role']} single-role policies."
                )
            return stats

        except FileNotFoundError:
            raise CSVValidationError("Policies file not found.")
        except Exception as e:
            if isinstance(e, CSVValidationError):
                raise
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise CSVValidationError(f"Unexpected error: {e}")

    def process_ingestion(
        self,
        assignments_file: Path,
        policies_file: Path | None = None,
    ) -> IngestResponse:
        self.user_states = {}
        self.all_user_states = {}
        self.policies = []
        self.last_ingest = None
        self.assignment_errors = []
        self.policy_errors = []
        self.policies_hash = ""

        assign_stats = self._ingest_assignments(assignments_file)

        policy_stats = {}
        if policies_file is not None:
            policy_stats = self._ingest_policies(policies_file)
        else:
            default_policy_path = settings.seed_dir / "toxic_policies.csv"
            if default_policy_path.exists():
                logger.info("Loading default policies from seed data")
                policy_stats = self._ingest_policies(default_policy_path)
            else:
                logger.error("No policies file provided and no seed data found")
                self.policies = []
                policy_stats = {
                    "total_policy_rows": 0,
                    "valid_policies": 0,
                    "corrupt_policies": 0,
                    "filtered_policies_single_role": 0,
                }

        total_active_roles = 0
        all_active_roles_set = set()
        single_role_users = 0
        active_user_count = 0

        for _, state in self.all_user_states.items():
            if state.status == AssignmentStatus.ACTIVE:
                active_user_count += 1
                if len(state.active_roles) <= 1:
                    single_role_users += 1

                total_active_roles += len(state.active_roles)
                all_active_roles_set.update(state.active_roles.keys())

        response = IngestResponse(
            total_assignment_rows=assign_stats["total_assignment_rows"],
            valid_assignment_rows=assign_stats["valid_assignment_rows"],
            corrupt_assignment_rows=assign_stats["corrupt_assignment_rows"],
            total_policy_rows=policy_stats["total_policy_rows"],
            valid_policies=policy_stats["valid_policies"],
            corrupt_policies=policy_stats["corrupt_policies"],
            filtered_policies_single_role=policy_stats["filtered_policies_single_role"],
            users_processed=assign_stats["total_users_found"],
            active_users=active_user_count,
            inactive_users=assign_stats["inactive_users_found"],
            users_with_single_role_filtered=single_role_users,
            total_active_roles=total_active_roles,
            unique_active_roles=len(all_active_roles_set),
        )

        self.last_ingest = response
        logger.info(f"Ingestion complete: {response.model_dump(exclude_none=True)}")
        return response

    def get_all_user_states(self) -> dict[str, UserRoleState]:
        return self.user_states

    def get_full_user_state(self, user_id: str) -> UserRoleState | None:
        return self.all_user_states.get(user_id)

    def get_all_policies(self) -> list[ToxicPolicy]:
        return self.policies

    def get_policies_hash(self) -> str:
        return self.policies_hash

    def _update_policies_hash(self) -> None:
        sorted_policies = sorted(self.policies, key=lambda p: p.policy_id)
        policy_data = [
            {
                "policy_id": p.policy_id,
                "description": p.description,
                "roles": sorted(list(p.roles)),
            }
            for p in sorted_policies
        ]
        json_str = json.dumps(policy_data, sort_keys=True)
        self.policies_hash = hashlib.sha256(json_str.encode()).hexdigest()[:16]

    def reset(self) -> None:
        self.policies = []
        self.user_states = {}
        self.all_user_states = {}
        self.last_ingest = None
        self.assignment_errors = []
        self.policy_errors = []
        logger.info("IngSestion service reset")
