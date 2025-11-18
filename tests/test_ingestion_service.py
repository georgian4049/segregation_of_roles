"""
Unit tests for the IngestionService.

These tests validate CSV parsing, error handling, and UserRoleState creation logic.
We use the `tmp_path` fixture provided by pytest to create temporary CSV files
for the service to ingest, ensuring our tests don't rely on the physical
`data/` directory.
"""
import pytest
from pathlib import Path
from src.services.ingestion import IngestionService, CSVValidationError
from src.models import AssignmentStatus

# Content for our mock CSV files
# Removed trailing newline inside the triple quotes to prevent extra empty row
SMALL_ASSIGNMENTS_CONTENT = """user_id,name,email,department,status,role,source_system,granted_at_iso
u1,Ana Silva,ana@bank.tld,Payments,active,PaymentsAdmin,Okta,2025-06-01T10:00:00Z
u1,Ana Silva,ana@bank.tld,Payments,active,TradingDesk,Okta,2025-06-02T10:00:00Z
u2,Lee Chen,lee@bank.tld,Trading,active,Root,AWS,2024-12-01T10:00:00Z
u2,Lee Chen,lee@bank.tld,Trading,active,OktaSuperAdmin,Okta,2024-12-15T10:00:00Z
u3,Sam Roy,sam@bank.tld,Security,inactive,OktaSuperAdmin,Okta,2024-05-01T10:00:00Z
u4,Maria Garcia,maria@bank.tld,Finance,active,FinanceApprover,SAP,2024-08-01T09:00:00Z
u4,Maria Garcia,maria@bank.tld,Finance,active,PaymentsAdmin,Okta,2024-08-15T09:00:00Z
u5,John Smith,john@bank.tld,IT,active,HelpdeskTier1,Okta,2024-01-10T09:00:00Z""" 

SMALL_ASSIGNMENTS_ERROR_CONTENT = """user_id,name,email,department,status,role,source_system,granted_at_iso
u1,Ana Silva,ana@bank.tld,Payments,active,PaymentsAdmin,Okta,2025-06-01T10:00:00Z
u5,John Smith,john@bank.tld,IT,active,2024-01-10T09:00:00Z
u2,Lee Chen,lee@bank.tld,Trading,active,Root,AWS,not-a-date""" 

SMALL_POLICIES_CONTENT = """policy_id,description,roles
P1,Cross-functional conflict,"[""PaymentsAdmin"", ""TradingDesk""]"
P2,Excessive infrastructure access,"[""Root"", ""OktaSuperAdmin""]"
P3,Maker-checker violation,"[""FinanceApprover"", ""PaymentsAdmin""]" """ 

SMALL_POLICIES_ERROR_CONTENT = """policy_id,description,roles
P1,Cross-functional conflict,"[""PaymentsAdmin"", ""TradingDesk""]"
P2,Excessive infrastructure access,"[""Root""]"
P3,Maker-checker violation,"[""FinanceApprover"",""PaymentsAdmin""]"
P4,Corrupt,,""" 

@pytest.fixture
def service() -> IngestionService:
    """Returns a fresh IngestionService instance for each test."""
    return IngestionService()

@pytest.fixture
def assignments_file(tmp_path: Path) -> Path:
    """Creates a temporary assignments.csv file and returns its path."""
    file_path = tmp_path / "assignments.csv"
    # strip() ensures no trailing newline confusion
    file_path.write_text(SMALL_ASSIGNMENTS_CONTENT.strip())
    return file_path

@pytest.fixture
def policies_file(tmp_path: Path) -> Path:
    """Creates a temporary policies.csv file and returns its path."""
    file_path = tmp_path / "policies.csv"
    # strip() ensures no trailing newline confusion
    file_path.write_text(SMALL_POLICIES_CONTENT.strip())
    return file_path

def test_ingest_assignments_happy_path(service: IngestionService, assignments_file: Path):
    """
    Tests successful ingestion of a valid assignments.csv.
    Validates user aggregation, status handling, and filtering.
    """
    stats = service._ingest_assignments(assignments_file)

    # Check stats
    assert stats["total_assignment_rows"] == 8
    assert stats["valid_assignment_rows"] == 8
    assert stats["corrupt_assignment_rows"] == 0
    assert stats["total_users_found"] == 5
    assert stats["inactive_users_found"] == 1
    assert not service.assignment_errors

    # Check all_user_states (includes inactive and single-role users)
    assert len(service.all_user_states) == 5
    assert "u1" in service.all_user_states
    assert "u3" in service.all_user_states
    assert "u5" in service.all_user_states

    # Check user_states (filtered for active AND multi-role)
    assert len(service.user_states) == 3
    assert "u1" in service.user_states  # Ana, active, 2 roles
    assert "u2" in service.user_states  # Lee, active, 2 roles
    assert "u4" in service.user_states  # Maria, active, 2 roles
    
    # Check filtered users
    assert "u3" not in service.user_states  # Sam is inactive
    assert "u5" not in service.user_states  # John is active but only 1 role

    # Spot-check user state
    ana = service.all_user_states["u1"]
    assert ana.status == AssignmentStatus.ACTIVE
    assert len(ana.active_roles) == 2
    assert "PaymentsAdmin" in ana.active_roles
    assert ana.active_roles["TradingDesk"].source_system == "Okta"

    sam = service.all_user_states["u3"]
    assert sam.status == AssignmentStatus.INACTIVE

def test_ingest_assignments_with_errors(service: IngestionService, tmp_path: Path):
    """Tests ingestion of a partially corrupt assignments file."""
    file_path = tmp_path / "assign_errors.csv"
    file_path.write_text(SMALL_ASSIGNMENTS_ERROR_CONTENT)
    
    stats = service._ingest_assignments(file_path)

    # Check stats
    assert stats["total_assignment_rows"] == 3
    assert stats["valid_assignment_rows"] == 1  # Only u1 is valid
    assert stats["corrupt_assignment_rows"] == 2
    
    # Check error log
    assert len(service.assignment_errors) == 2
    
    # Check for u5 error - row with missing columns
    # The error message from pydantic varies but usually mentions input or validation
    u5_err = service.assignment_errors[0]
    assert u5_err["line"] == 3
    # It failed validation. We accept any validation error string as success
    assert u5_err["error"]
    
    # Check for u2 error - invalid date
    u2_err = service.assignment_errors[1]
    assert u2_err["line"] == 4
    assert "error" in u2_err["error"]

    # Check that valid data was still processed
    assert len(service.all_user_states) == 1
    assert "u1" in service.all_user_states

def test_ingest_assignments_missing_column(service: IngestionService, tmp_path: Path):
    """Tests that ingestion fails hard if a required column is missing."""
    file_path = tmp_path / "missing_col.csv"
    file_path.write_text("user_id,name,email\n1,test,test@test.com")

    with pytest.raises(CSVValidationError, match="Missing required columns"):
        service._ingest_assignments(file_path)

def test_ingest_policies_happy_path(service: IngestionService, policies_file: Path):
    """Tests successful ingestion of a valid policies.csv."""
    stats = service._ingest_policies(policies_file)

    assert stats["total_policy_rows"] == 3
    assert stats["valid_policies"] == 3
    assert stats["corrupt_policies"] == 0
    assert stats["filtered_policies_single_role"] == 0
    assert not service.policy_errors

    assert len(service.policies) == 3
    assert service.policies[0].policy_id == "P1"
    assert service.policies[0].roles == {"PaymentsAdmin", "TradingDesk"}
    assert service.policies_hash  # Hash should be generated

def test_ingest_policies_with_errors_and_filters(service: IngestionService, tmp_path: Path):
    """Tests ingestion of policies with single-role (filtered) and corrupt rows."""
    file_path = tmp_path / "policy_errors.csv"
    file_path.write_text(SMALL_POLICIES_ERROR_CONTENT.strip())

    stats = service._ingest_policies(file_path)

    assert stats["total_policy_rows"] == 4
    assert stats["valid_policies"] == 2
    assert stats["corrupt_policies"] == 1
    assert stats["filtered_policies_single_role"] == 1
    
    assert len(service.policy_errors) == 2
    
    # Check P2 (filtered)
    assert service.policy_errors[0]["line"] == 3
    assert "filtered" in service.policy_errors[0]["error"]
    
    # Check P4 (corrupt)
    assert service.policy_errors[1]["line"] == 5
    assert "Could not extract any roles" in service.policy_errors[1]["error"] # Custom error from logic
    
    assert len(service.policies) == 2
    assert service.policies[0].policy_id == "P1"
    assert service.policies[1].policy_id == "P3"

def test_process_ingestion_main_method(
    service: IngestionService, assignments_file: Path, policies_file: Path
):
    """Tests the main public method that combines all ingestion logic."""
    response = service.process_ingestion(assignments_file, policies_file)
    
    assert service.last_ingest is not None
    assert response is service.last_ingest

    # Validate stats from IngestResponse
    assert response.users_processed == 5
    assert response.active_users == 4
    assert response.inactive_users == 1
    assert response.users_with_single_role_filtered == 1  # John (u5)
    
    assert response.valid_assignment_rows == 8
    assert response.corrupt_assignment_rows == 0
    
    assert response.valid_policies == 3
    assert response.corrupt_policies == 0
    
    assert len(service.get_all_policies()) == 3
    assert len(service.get_all_user_states()) == 3 # Filtered list
    assert len(service.all_user_states) == 5     # Unfiltered list