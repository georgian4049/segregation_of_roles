"""
Unit tests for the DetectionEngine.

These tests focus on the core business logic:
- Does it correctly identify a violation?
- Does it correctly ignore non-violations?
- Does it correctly aggregate multiple violations for a single user?
"""
import pytest
from src.services.detection import DetectionEngine
from src.services.policy_store import PolicyStore
from src.models import ToxicPolicy, UserRoleState
from tests.conftest import (
    user_ana_violates_p1,
    user_lee_violates_p2,
    user_john_no_violation,
    user_maria_multi_violation,
    populated_policy_store,
    sample_policy_p1,
)

@pytest.fixture
def engine(populated_policy_store: PolicyStore) -> DetectionEngine:
    """Returns a DetectionEngine initialized with sample policies."""
    return DetectionEngine(populated_policy_store)

def test_detect_violations_finds_matches(
    engine: DetectionEngine,
    user_ana_violates_p1: UserRoleState,
    user_lee_violates_p2: UserRoleState,
    user_john_no_violation: UserRoleState
):
    """
    Tests that the engine finds violations for users who match policies
    and ignores users who do not.
    """
    user_states = {
        "u1": user_ana_violates_p1,
        "u2": user_lee_violates_p2,
        "u5": user_john_no_violation,
    }
    
    profiles = engine.detect_violations(user_states)

    assert len(profiles) == 2
    assert "u1" in profiles
    assert "u2" in profiles
    assert "u5" not in profiles  # u5 has no violations

    # Check Ana's (u1) profile
    ana_profile = profiles["u1"]
    assert ana_profile.user.user_id == "u1"
    assert len(ana_profile.violated_policies) == 1
    assert ana_profile.violated_policies[0].policy_id == "P1"
    assert ana_profile.conflicting_role_set == {"PaymentsAdmin", "TradingDesk"}
    assert ana_profile.reason == "User violates 1 policies: P1"

    # Check Lee's (u2) profile
    lee_profile = profiles["u2"]
    assert lee_profile.user.user_id == "u2"
    assert len(lee_profile.violated_policies) == 1
    assert lee_profile.violated_policies[0].policy_id == "P2"
    assert lee_profile.conflicting_role_set == {"Root", "OktaSuperAdmin"}
    assert lee_profile.reason == "User violates 1 policies: P2"

def test_detect_violations_finds_no_matches(
    engine: DetectionEngine,
    user_john_no_violation: UserRoleState
):
    """Tests that no profiles are returned when no users are in violation."""
    user_states = {"u5": user_john_no_violation}
    profiles = engine.detect_violations(user_states)
    assert len(profiles) == 0

def test_detect_violations_handles_no_policies(user_ana_violates_p1: UserRoleState):
    """Tests that the engine returns no violations if no policies are loaded."""
    empty_store = PolicyStore()
    engine = DetectionEngine(empty_store)
    
    user_states = {"u1": user_ana_violates_p1} 
    
    profiles = engine.detect_violations(user_states)
    assert len(profiles) == 0

def test_detect_violations_aggregates_multiple_violations(
    user_maria_multi_violation: UserRoleState
):
    """
    Tests the key feature: aggregating multiple policy violations
    for a single user into one profile.
    """
    # Create a custom policy store for this test
    policy_store = PolicyStore()
    policy_store.update_policies([
        ToxicPolicy(policy_id="P1", description="...", roles={"PaymentsAdmin", "TradingDesk"}),
        ToxicPolicy(policy_id="P3", description="...", roles={"FinanceApprover", "PaymentsAdmin"}),
        ToxicPolicy(policy_id="P99", description="...", roles={"Non", "Existent"}),
    ])
    engine = DetectionEngine(policy_store)

    user_states = {"u4": user_maria_multi_violation}
    profiles = engine.detect_violations(user_states)

    # We should get exactly one profile back
    assert len(profiles) == 1
    assert "u4" in profiles

    maria_profile = profiles["u4"]
    
    # It should detect *both* violations
    assert len(maria_profile.violated_policies) == 2
    policy_ids = {p.policy_id for p in maria_profile.violated_policies}
    assert policy_ids == {"P1", "P3"}

    # The conflicting role set should be the union of all roles from all violations
    assert maria_profile.conflicting_role_set == {
        "PaymentsAdmin", "TradingDesk", "FinanceApprover"
    }

    # The reason should be dynamically generated
    assert maria_profile.reason == "User violates 2 policies: P1, P3"