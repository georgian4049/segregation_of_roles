"""
Unit tests for the LLMService.

These tests use `pytest-mock` (via the `mocker` fixture) to patch dependencies
like the Bedrock client and application settings. This allows us to test
the service's logic (e.g., fallback behavior) without making real API calls.
"""
import pytest
import json
from unittest.mock import MagicMock
from src.services.llm_service import (
    LLMService, 
    MockLLMProvider, 
    BedrockProvider
)
from src.models import UserViolationProfile
from tests.conftest import profile_ana_p1

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_settings(mocker):
    """Mocks the global settings object."""
    mock_set = mocker.patch("src.services.llm_service.settings")
    mock_set.use_mock_llm = False
    mock_set.llm_provider = "bedrock"
    mock_set.bedrock_model_id = "anthropic.claude-3-haiku-20240307-v1:0"
    mock_set.bedrock_model_temperature = 0.1
    mock_set.bedrock_model_max_tokens = 100
    mock_set.aws_region = "us-east-1"
    mock_set.has_aws_credentials = False
    return mock_set

@pytest.fixture
def mock_boto3(mocker):
    """Mocks the boto3 client and session."""
    mock_session_cls = mocker.patch("src.services.llm_service.boto3.Session")
    mock_session = MagicMock()
    mock_client = MagicMock()
    mock_session.client.return_value = mock_client
    mock_session_cls.return_value = mock_session
    return mock_client

async def test_mock_provider_generates_dynamic_json(profile_ana_p1: UserViolationProfile):
    """Tests that the mock provider correctly uses the profile to build a response."""
    provider = MockLLMProvider()
    response_str = await provider.generate("", 0, profile=profile_ana_p1)
    
    assert isinstance(response_str, str)
    data = json.loads(response_str)
    
    assert data["risk"] == "User in 'Payments' violates 1 policies."
    # The conflicting_role_set is a set, so order isn't guaranteed.
    # We must check for either role.
    assert data["action"] in [
        "Revoke 'PaymentsAdmin' role.", "Revoke 'TradingDesk' role."
    ]
    assert data["rationale"] == "This action resolves policy violations: P1."

def test_llm_service_uses_mock_when_flag_is_true(mock_settings):
    """Tests that USE_MOCK_LLM=True forces the MockLLMProvider."""
    mock_settings.use_mock_llm = True
    
    service = LLMService()
    
    assert isinstance(service.provider, MockLLMProvider)
    assert service.status["using_mock"] is True
    assert service.status["fallback"] is False

def test_llm_service_uses_bedrock_by_default(mock_settings, mock_boto3):
    """Tests that the BedrockProvider is initialized by default."""
    service = LLMService()
    
    assert isinstance(service.provider, BedrockProvider)
    assert service.status["using_mock"] is False
    assert service.status["fallback"] is False
    assert service.status["model_identifier"] == "bedrock:anthropic.claude-3-haiku-20240307-v1:0"
    mock_boto3.Session.assert_called_once()

def test_llm_service_falls_back_to_mock_on_bedrock_init_error(mock_settings, mocker):
    """
    Tests that if BedrockProvider fails to initialize (e.g., bad credentials),
    the service gracefully falls back to the MockLLMProvider.
    """
    # Force the BedrockProvider's __init__ to fail
    mocker.patch(
        "src.services.llm_service.BedrockProvider.__init__",
        side_effect=RuntimeError("Test init failed")
    )
    
    service = LLMService()
    
    assert isinstance(service.provider, MockLLMProvider)
    assert service.status["using_mock"] is True
    assert service.status["fallback"] is True  # Key check!

def test_parse_and_validate_response_happy_path():
    """Tests that the parser extracts valid JSON from surrounding text."""
    service = LLMService()
    good_json = """
    Here is the JSON object you requested:
    {
        "risk": "This is a major risk.",
        "action": "Revoke 'Root'.",
        "rationale": "This is the reason."
    }
    Thank you.
    """
    risk, action, rationale = service._parse_and_validate_response(good_json)
    assert risk == "This is a major risk."
    assert action == "Revoke 'Root'."
    assert rationale == "This is the reason."

def test_parse_and_validate_response_missing_keys():
    """Tests that the parser fails if the JSON is valid but missing keys."""
    service = LLMService()
    bad_json = '{"risk": "This is a major risk.", "action": "Revoke \'Root\'."}'
    
    with pytest.raises(ValueError, match="missing required keys"):
        service._parse_and_validate_response(bad_json)

def test_parse_and_validate_response_invalid_json():
    """Tests that the parser fails if the text is not valid JSON."""
    service = LLMService()
    invalid_json = '{"risk": "This is a major risk", '
    
    with pytest.raises(ValueError, match="JSON parsing failed"):
        service._parse_and_validate_response(invalid_json)

def test_redact_email():
    """Tests the email redaction logic."""
    service = LLMService()
    assert service._redact_email("ana.silva@bank.tld") == "a***@bank.tld"
    assert service._redact_email("a@b.com") == "a***@b.com"
    assert service._redact_email("bad-email-format") == "***@***"
    assert service._redact_email("") == "***@***"