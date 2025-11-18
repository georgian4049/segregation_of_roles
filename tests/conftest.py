"""
Shared fixtures for pytest.

This file provides reusable, modular data for use across all test files.
Fixtures are a core feature of pytest, enabling dependency injection for tests.
"""
import pytest
from datetime import datetime
from src.models import (
    ToxicPolicy, 
    UserRoleState, 
    RoleAssignment, 
    AssignmentStatus,
    UserViolationProfile
)
from src.services.policy_store import PolicyStore

# --- Policy Fixtures ---

@pytest.fixture
def sample_policy_p1() -> ToxicPolicy:
    """Returns a sample P1 policy."""
    return ToxicPolicy(
        policy_id="P1",
        description="Payments and Trading roles must not co-exist",
        roles={"PaymentsAdmin", "TradingDesk"}
    )

@pytest.fixture
def sample_policy_p2() -> ToxicPolicy:
    """Returns a sample P2 policy."""
    return ToxicPolicy(
        policy_id="P2",
        description="Incompatible cloud admin roles",
        roles={"Root", "OktaSuperAdmin"}
    )

@pytest.fixture
def sample_policies_list(sample_policy_p1, sample_policy_p2) -> list[ToxicPolicy]:
    """Returns a list of all sample policies."""
    return [sample_policy_p1, sample_policy_p2]

@pytest.fixture
def populated_policy_store(sample_policies_list) -> PolicyStore:
    """Returns a PolicyStore instance pre-filled with sample policies."""
    store = PolicyStore()
    store.update_policies(sample_policies_list)
    return store

# --- User State Fixtures ---

def _create_role_assignment(role: str, system: str, days_ago: int) -> RoleAssignment:
    """Helper to create a RoleAssignment with a relative date."""
    return RoleAssignment(
        role=role,
        source_system=system,
        granted_at=datetime(2025, 1, 10 - days_ago)
    )

@pytest.fixture
def user_ana_violates_p1() -> UserRoleState:
    """Fixture for Ana (u1) - Active, 2 conflicting roles."""
    roles = {
        "PaymentsAdmin": _create_role_assignment("PaymentsAdmin", "Okta", 5),
        "TradingDesk": _create_role_assignment("TradingDesk", "Okta", 10),
    }
    return UserRoleState(
        user_id="u1",
        name="Ana Silva",
        email="ana@bank.tld",
        department="Payments",
        status=AssignmentStatus.ACTIVE,
        active_roles=roles,
        source_systems=["Okta"]
    )

@pytest.fixture
def user_lee_violates_p2() -> UserRoleState:
    """Fixture for Lee (u2) - Active, 2 conflicting roles."""
    roles = {
        "Root": _create_role_assignment("Root", "AWS", 20),
        "OktaSuperAdmin": _create_role_assignment("OktaSuperAdmin", "Okta", 30),
    }
    return UserRoleState(
        user_id="u2",
        name="Lee Chen",
        email="lee@bank.tld",
        department="Trading",
        status=AssignmentStatus.ACTIVE,
        active_roles=roles,
        source_systems=["AWS", "Okta"]
    )

@pytest.fixture
def user_john_no_violation() -> UserRoleState:
    """Fixture for John (u5) - Active, 1 role (no violation)."""
    roles = {
        "HelpdeskTier1": _create_role_assignment("HelpdeskTier1", "Okta", 100),
    }
    return UserRoleState(
        user_id="u5",
        name="John Smith",
        email="john@bank.tld",
        department="IT",
        status=AssignmentStatus.ACTIVE,
        active_roles=roles,
        source_systems=["Okta"]
    )

@pytest.fixture
def user_sam_inactive() -> UserRoleState:
    """Fixture for Sam (u3) - Inactive, 1 role."""
    roles = {
        "OktaSuperAdmin": _create_role_assignment("OktaSuperAdmin", "Okta", 200),
    }
    return UserRoleState(
        user_id="u3",
        name="Sam Roy",
        email="sam@bank.tld",
        department="Security",
        status=AssignmentStatus.INACTIVE,
        active_roles=roles,
        source_systems=["Okta"]
    )

@pytest.fixture
def user_maria_multi_violation() -> UserRoleState:
    """
    Fixture for Maria (u4) - Active, 2 roles that violate P1 (mock) and P3.
    This tests aggregation.
    """
    roles = {
        "FinanceApprover": _create_role_assignment("FinanceApprover", "SAP", 50),
        "PaymentsAdmin": _create_role_assignment("PaymentsAdmin", "Okta", 60),
        "TradingDesk": _create_role_assignment("TradingDesk", "Okta", 70),
    }
    return UserRoleState(
        user_id="u4",
        name="Maria Garcia",
        email="maria@bank.tld",
        department="Finance",
        status=AssignmentStatus.ACTIVE,
        active_roles=roles,
        source_systems=["SAP", "Okta"]
    )

@pytest.fixture
def profile_ana_p1(user_ana_violates_p1, sample_policy_p1) -> UserViolationProfile:
    """
    A complete, ready-to-use UserViolationProfile for Ana violating P1.
    This is useful for testing the LLM and prompt services.
    """
    return UserViolationProfile(
        finding_id="FINDING-U1-12345",
        user=user_ana_violates_p1,
        violated_policies=[sample_policy_p1],
        conflicting_role_set={"PaymentsAdmin", "TradingDesk"},
        severity="high",
        reason="User violates 1 policies: P1",
        suggested_action="revoke one role"
    )