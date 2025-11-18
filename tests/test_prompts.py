"""
Unit tests for the prompt building logic in `src/prompts/prompts.py`.

These tests ensure that the context from a UserViolationProfile is correctly
injected into the master prompt template.
"""
from src.prompts.prompts import build_smart_remediation_prompt
from src.models import UserViolationProfile
from tests.conftest import profile_ana_p1

def test_build_smart_remediation_prompt_populates_all_fields(
    profile_ana_p1: UserViolationProfile
):
    """
    Tests that all placeholders in the prompt are correctly filled
    with data from the UserViolationProfile.
    """
    prompt = build_smart_remediation_prompt(profile_ana_p1)

    # Check that no placeholders remain
    assert "{{DEPARTMENT}}" not in prompt
    assert "{{ROLES_LIST}}" not in prompt
    assert "{{VIOLATIONS_LIST}}" not in prompt

    # Check that user data is injected
    assert profile_ana_p1.user.department in prompt  # "Payments"
    
    # Check that role data is injected
    assert "PaymentsAdmin" in prompt
    assert "TradingDesk" in prompt
    assert profile_ana_p1.user.active_roles["PaymentsAdmin"].source_system in prompt # "Okta"
    assert str(profile_ana_p1.user.active_roles["TradingDesk"].granted_at.date()) in prompt

    # Check that violation data is injected
    assert profile_ana_p1.violated_policies[0].policy_id in prompt  # "P1"
    assert profile_ana_p1.violated_policies[0].description in prompt