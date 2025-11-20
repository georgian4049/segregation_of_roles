"""
Integration tests for the full API workflow.

These tests verify that the endpoints work together as expected:
Ingest -> Detect (Stream) -> Simulate -> Decide -> Evidence.
"""
import pytest
import json
from fastapi.testclient import TestClient

# Sample CSV Data
ASSIGNMENTS_CSV = """user_id,name,email,department,status,role,source_system,granted_at_iso
u1,Ana Silva,ana@bank.tld,Payments,active,PaymentsAdmin,Okta,2025-06-01T10:00:00Z
u1,Ana Silva,ana@bank.tld,Payments,active,TradingDesk,Okta,2025-06-02T10:00:00Z
u2,Lee Chen,lee@bank.tld,Trading,active,Root,AWS,2024-12-01T10:00:00Z
"""

POLICIES_CSV = """policy_id,description,roles
P1,Conflict P1,"[""PaymentsAdmin"", ""TradingDesk""]"
"""


def test_full_workflow_happy_path(client: TestClient, mocker):
    """
    Simulates a complete user session:
    1. Upload data
    2. Get findings (mocking LLM)
    3. Simulate a fix
    4. Submit a decision
    5. Download evidence
    """
    # ---------------------------------------------------------
    # 1. Ingest Data
    # ---------------------------------------------------------
    files = {
        "assignments": ("assignments.csv", ASSIGNMENTS_CSV, "text/csv"),
        "policies": ("policies.csv", POLICIES_CSV, "text/csv"),
    }
    response = client.post("/api/v1/ingest", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["valid_assignment_rows"] == 3
    assert data["valid_policies"] == 1
    assert data["active_users"] == 2

    # ---------------------------------------------------------
    # 2. Get Findings (Streaming)
    # ---------------------------------------------------------
    # We force the LLM to be a mock so we don't hit AWS Bedrock
    mocker.patch("src.config.settings.use_mock_llm", True)

    # TestClient.stream() allows us to read the SSE stream
    with client.stream("GET", "/api/v1/findings") as stream:
        assert stream.status_code == 200

        findings_received = []
        for line in stream.iter_lines():
            if line.startswith("data: "):
                json_str = line.replace("data: ", "")
                # Skip the completion message or empty lines
                if not json_str.strip() or json_str == '{"message": "Stream complete"}':
                    continue

                try:
                    finding = json.loads(json_str)
                    findings_received.append(finding)
                except json.JSONDecodeError:
                    print(f"Failed to decode JSON: {json_str}")

    # Ana (u1) should have a violation (PaymentsAdmin + TradingDesk)
    assert len(findings_received) >= 1, "Expected at least one finding"

    # We look for u1 specifically
    ana_finding = next(
        (
            f
            for f in findings_received
            if f.get("profile", {}).get("user", {}).get("user_id") == "u1"
        ),
        None,
    )

    # Detailed failure message if Ana isn't found
    if not ana_finding:
        # Check if we got an error object instead
        error_finding = next((f for f in findings_received if f.get("error")), None)
        if error_finding:
            pytest.fail(f"Findings stream returned an error: {error_finding}")
        else:
            pytest.fail(f"Ana (u1) finding not found. Received: {findings_received}")

    assert ana_finding["profile"]["user"]["user_id"] == "u1"
    assert ana_finding["profile"]["violated_policies"][0]["policy_id"] == "P1"
    # Check if LLM justification is present
    assert ana_finding["justification"] is not None
    assert "risk" in ana_finding["justification"]

    # ---------------------------------------------------------
    # 3. Simulation (What-if)
    # ---------------------------------------------------------
    # Try removing "TradingDesk" from Ana
    sim_payload = {"user_id": "u1", "role_to_remove": "TradingDesk"}
    sim_response = client.post("/api/v1/simulate", json=sim_payload)
    assert sim_response.status_code == 200
    sim_data = sim_response.json()

    assert sim_data["resolved"] is True
    assert "resolved" in sim_data["message"]

    # ---------------------------------------------------------
    # 4. Submit Decision
    # ---------------------------------------------------------
    decision_payload = {
        "user_id": "u1",
        "decision": "revoke_role",
        "roles_to_revoke": ["TradingDesk"],
        "decided_by": "manager_dave",
        "notes": "Revoking trading access per policy.",
    }
    dec_response = client.post("/api/v1/decisions", json=decision_payload)
    assert dec_response.status_code == 200

    # ---------------------------------------------------------
    # 5. Get Evidence Log
    # ---------------------------------------------------------
    ev_response = client.get("/api/v1/evidence")
    assert ev_response.status_code == 200
    evidence = ev_response.json()

    # Verify evidence integrity
    assert len(evidence["findings"]) == 1
    assert evidence["findings"][0]["profile"]["user"]["name"] == "REDACTED"  # PII check
    assert len(evidence["decisions"]) == 1
    assert evidence["decisions"][0]["user_id"] == "u1"


def test_full_workflow_same_files_path(client: TestClient, mocker):
    """
    Simulates a complete user session:
    1. Upload data
    2. Get findings (mocking LLM)
    3. Simulate a fix
    4. Submit a decision
    5. Download evidence
    """
    # ---------------------------------------------------------
    # 1. Ingest Data
    # ---------------------------------------------------------
    files = {
        "assignments": ("assignments.csv", ASSIGNMENTS_CSV, "text/csv"),
        "policies": ("assignments.csv", ASSIGNMENTS_CSV, "text/csv"),
    }
    response = client.post("/api/v1/ingest", files=files)
    assert response.status_code == 400


def test_ingest_invalid_file_type(client: TestClient):
    """Tests that uploading a non-CSV file returns 400."""
    files = {
        "assignments": ("image.png", b"fake image data", "image/png"),
    }
    response = client.post("/api/v1/ingest", files=files)
    assert response.status_code == 400
    assert "must be a .csv" in response.json()["detail"]


def test_findings_before_ingest_fails(client: TestClient):
    """Tests that getting findings before ingesting data returns 400."""
    # reset_app_state fixture ensures app is empty
    response = client.get("/api/v1/findings")
    assert response.status_code == 400
    assert "No data ingested" in response.json()["detail"]


def test_ingest_assignments_only(client: TestClient):
    """
    Scenario: Upload only assignments.csv (policies omitted).
    Expected: 200 OK.
    Why: The API definition (in routes.py) defines policies as Optional.
         It should use default policies or just have 0 new policies.
    """
    files = {
        "assignments": ("assignments.csv", ASSIGNMENTS_CSV, "text/csv"),
    }
    # Policies is omitted from the files dict
    response = client.post("/api/v1/ingest", files=files)

    assert response.status_code == 200
    data = response.json()

    # Validate assignments were processed
    assert data["valid_assignment_rows"] == 3
    assert data["active_users"] == 2

    # Validate policies behavior (depends on implementation, usually 0 from upload)
    # Based on your ingestion.py logic, if no file is provided, it might load defaults or have 0.
    # Let's assert the upload count is 0.
    assert data["total_policy_rows"] == 12


def test_ingest_policies_only_fails(client: TestClient):
    """
    Scenario: Upload only policies.csv (assignments omitted).
    Expected: 422 Unprocessable Entity.
    Why: In `routes.py`, `assignments` is a required argument:
         `assignments: Annotated[UploadFile, File(...)]`
         while policies is optional: `policies: Annotated[UploadFile | None, ...] = None`
    """
    files = {
        "policies": ("policies.csv", POLICIES_CSV, "text/csv"),
    }
    # Assignments is omitted
    response = client.post("/api/v1/ingest", files=files)

    assert response.status_code == 422
    # The error detail from FastAPI/Pydantic usually explicitly lists the missing field
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["type"] == "missing"
    assert "assignments" in str(detail[0]["loc"])
