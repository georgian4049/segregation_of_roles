"""
Test suite specifically for verifying HTTP status codes and error handling.
This ensures the API adheres to RESTful standards and provides useful error messages.
"""
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

# --- 400 Bad Request Tests ---


def test_ingest_invalid_extension():
    """
    Scenario: User uploads a file that is not a CSV.
    Expected: 400 Bad Request.
    """
    files = {"assignments": ("test.txt", "some content", "text/plain")}
    response = client.post("/api/v1/ingest", files=files)
    assert response.status_code == 400
    assert "must be a .csv file" in response.json()["detail"]


def test_simulate_invalid_role_removal():
    """
    Scenario: User tries to remove a role they don't actually have.
    Expected: 400 Bad Request (Logic Error).
    """
    # 1. Setup state (Ingest data first)
    csv_content = "user_id,name,email,department,status,role,source_system,granted_at_iso\nu1,Ana,a@b.com,IT,active,Admin,Okta,2023-01-01T00:00:00Z"
    client.post(
        "/api/v1/ingest", files={"assignments": ("a.csv", csv_content, "text/csv")}
    )

    # 2. Attempt invalid simulation
    payload = {"user_id": "u1", "role_to_remove": "NonExistentRole"}
    response = client.post("/api/v1/simulate", json=payload)

    assert response.status_code == 400
    assert "not active for user" in response.json()["detail"]


def test_findings_without_ingestion():
    """
    Scenario: User calls /findings before uploading data.
    Expected: 400 Bad Request (State Error).
    """
    # Clear state first (using the reset endpoint logic or just a fresh client if not persistent)
    # Note: In our conftest, we reset state automatically.
    response = client.get("/api/v1/findings")
    assert response.status_code == 400
    assert "No data ingested" in response.json()["detail"]


# --- 404 Not Found Tests ---


def test_simulate_unknown_user():
    """
    Scenario: User tries to simulate on a user_id that doesn't exist.
    Expected: 404 Not Found.
    """
    # 1. Ingest basic data
    csv_content = "user_id,name,email,department,status,role,source_system,granted_at_iso\nu1,Ana,a@b.com,IT,active,Admin,Okta,2023-01-01T00:00:00Z"
    client.post(
        "/api/v1/ingest", files={"assignments": ("a.csv", csv_content, "text/csv")}
    )

    # 2. Simulate on wrong ID
    payload = {"user_id": "GHOST_USER", "role_to_remove": "Admin"}
    response = client.post("/api/v1/simulate", json=payload)

    assert response.status_code == 404
    assert "User GHOST_USER not found" in response.json()["detail"]


def test_decision_unknown_user():
    """
    Scenario: User tries to submit a decision for a user not in the findings cache.
    Expected: 404 Not Found.
    """
    payload = {
        "user_id": "unknown_user",
        "decision": "accept_risk",
        "decided_by": "test",
    }
    response = client.post("/api/v1/decisions", json=payload)
    assert response.status_code == 404
    assert "not found in the current scan" in response.json()["detail"]


# --- 422 Unprocessable Entity (Validation Error) ---


def test_ingest_missing_files():
    """
    Scenario: Request to /ingest without the required 'assignments' file.
    Expected: 422 Unprocessable Entity (FastAPI default for missing required fields).
    """
    # Sending empty body/no files
    response = client.post("/api/v1/ingest")
    assert response.status_code == 422
    # Verify it's a standard Pydantic/FastAPI error structure
    data = response.json()
    assert data["detail"][0]["type"] == "missing"
    assert "assignments" in str(data["detail"])


def test_decision_invalid_enum():
    """
    Scenario: Submitting a decision value that isn't in the allowed list.
    Expected: 422 Unprocessable Entity.
    """
    payload = {
        "user_id": "u1",
        "decision": "burn_it_down",  # Invalid choice
        "decided_by": "test",
    }
    response = client.post("/api/v1/decisions", json=payload)
    assert response.status_code == 422
    assert "Input should be 'accept_risk', 'revoke_role' or 'investigate'" in str(
        response.json()["detail"]
    )


# --- 405 Method Not Allowed ---


def test_wrong_method_on_endpoint():
    """
    Scenario: Sending a GET request to a POST-only endpoint.
    Expected: 405 Method Not Allowed.
    """
    response = client.get("/api/v1/ingest")
    assert response.status_code == 405
    assert response.json()["detail"] == "Method Not Allowed"


def test_wrong_method_on_endpoint_findings():
    """
    Scenario: Sending a GET request to a POST-only endpoint.
    Expected: 405 Method Not Allowed.
    """
    response = client.post("/api/v1/findings")
    assert response.status_code == 405
    assert response.json()["detail"] == "Method Not Allowed"
