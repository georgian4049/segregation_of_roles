"""
LLM service for generating justifications.
"""
import logging
import re
import json
import asyncio
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Tuple, Any
from botocore.exceptions import ClientError
import boto3

from src.config import settings
from src.models import LLMJustification, UserViolationProfile
from src.prompts.prompts import build_smart_remediation_prompt
from src.evaluation.metrics import JsonComplianceMetric, HallucinationMetric

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(
        self, prompt: str, max_tokens: int, profile: UserViolationProfile | None = None
    ) -> str:
        """Generate text from LLM."""
        pass

    @abstractmethod
    def get_model_identifier(self) -> str:
        """Return model identifier for logging."""
        pass


class MockLLMProvider(LLMProvider):
    """
    Mock LLM provider for testing/demo.
    Now generates a DYNAMIC response based on the profile.
    """

    def get_model_identifier(self) -> str:
        return "mock-llm-v1-dynamic"

    async def generate(
        self, prompt: str, max_tokens: int, profile: UserViolationProfile | None = None
    ) -> str:
        """Generate dynamic mock JSON response based on profile."""
        logger.debug("Mock LLM generating dynamic response")
        await asyncio.sleep(0.1)  # Simulate network delay

        if not profile:
            # Fallback for any case where profile isn't passed
            return json.dumps(
                {
                    "risk": "No profile provided.",
                    "action": "Investigate.",
                    "rationale": "Profile was missing from context.",
                }
            )

        violated_policy_ids = ", ".join(
            [p.policy_id for p in profile.violated_policies]
        )
        conflicting_roles = list(profile.conflicting_role_set)
        role_to_revoke = (
            conflicting_roles[0] if conflicting_roles else "a_conflicting_role"
        )

        risk = f"User in '{profile.user.department}' violates {len(profile.violated_policies)} policies."
        action = f"Revoke '{role_to_revoke}' role."
        rationale = f"This action resolves policy violations: {violated_policy_ids}."

        return json.dumps({"risk": risk, "action": action, "rationale": rationale})


class BedrockProvider(LLMProvider):
    """
    AWS Bedrock provider.
    """

    def __init__(self, model_id: str, temperature: float, max_tokens: int):
        try:
            session_kwargs = {"region_name": settings.aws_region}

            if settings.has_aws_credentials:
                logger.info("Using explicit AWS credentials from environment")
                session_kwargs["aws_access_key_id"] = settings.aws_access_key_id
                session_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

                if settings.aws_session_token:
                    session_kwargs["aws_session_token"] = settings.aws_session_token
            else:
                logger.info("Using default AWS credential chain (CLI/IAM role)")

            session = boto3.Session(region_name=settings.aws_region)
            self.client = session.client("bedrock-runtime")
            self.model_id = model_id
            self.temperature = temperature
            self.default_max_tokens = max_tokens
            logger.info(f"BedrockProvider initialized for model: {self.model_id}")
        except Exception as e:
            logger.error(f"Failed to initialize Bedrock client: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize Bedrock client: {e}")

    def get_model_identifier(self) -> str:
        return f"bedrock:{self.model_id}"

    async def generate(
        self, prompt: str, max_tokens: int, profile: UserViolationProfile | None = None
    ) -> str:
        """Generate response using Bedrock's native formats."""
        final_max_tokens = max_tokens or self.default_max_tokens

        try:
            if "amazon.titan" in self.model_id:
                native_request = {
                    "inputText": prompt,
                    "textGenerationConfig": {
                        "maxTokenCount": final_max_tokens,
                        "temperature": self.temperature,
                        "stopSequences": [],
                    },
                }
                request_body = json.dumps(native_request)

            elif "anthropic.claude" in self.model_id:
                native_request = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": final_max_tokens,
                    "temperature": self.temperature,
                    "messages": [
                        {"role": "user", "content": [{"type": "text", "text": prompt}]}
                    ],
                }
                request_body = json.dumps(native_request)
            else:
                raise NotImplementedError(
                    f"Model format for {self.model_id} not implemented."
                )

            response = self.client.invoke_model(
                modelId=self.model_id,
                body=request_body,
                contentType="application/json",
                accept="application/json",
            )
            model_response = json.loads(response["body"].read())

            if "amazon.titan" in self.model_id:
                return model_response["results"][0]["outputText"]
            elif "anthropic.claude" in self.model_id:
                return model_response["content"][0]["text"]
            else:
                raise NotImplementedError(
                    f"Response parsing for {self.model_id} not implemented."
                )

        except ClientError as e:
            if e.response["Error"]["Code"] == "ValidationException":
                logger.error(
                    f"Bedrock ValidationException: {e}. Check if model is enabled in AWS."
                )
                raise RuntimeError(f"Bedrock ValidationException: {e}")
            else:
                logger.error(f"Bedrock ClientError: {e}", exc_info=True)
                raise RuntimeError(f"Bedrock ClientError: {e}")
        except Exception as e:
            logger.error(f"Bedrock generation error: {e}", exc_info=True)
            raise RuntimeError(f"Bedrock generation error: {e}")


class LLMService:
    def __init__(self):
        self.status: dict[str, Any] = {"provider": "uninitialized"}
        self._fallback_provider = MockLLMProvider()
        self.provider = self._init_provider()

    def _init_provider(self) -> LLMProvider:
        if settings.use_mock_llm:
            logger.info("Using Mock LLM provider")
            provider = self._fallback_provider
        elif settings.llm_provider == "bedrock":
            logger.info(
                f"Using Bedrock provider with model: {settings.bedrock_model_id}"
            )
            try:
                provider = BedrockProvider(
                    model_id=settings.bedrock_model_id,
                    temperature=settings.bedrock_model_temperature,
                    max_tokens=settings.bedrock_model_max_tokens,
                )
            except Exception as exc:
                logger.error(
                    "Bedrock initialization failed, falling back to mock: %s", exc
                )
                provider = self._fallback_provider
        else:
            logger.error(
                f"Unknown LLM provider '{settings.llm_provider}', falling back to mock."
            )
            provider = self._fallback_provider

        self.status = {
            "provider": provider.__class__.__name__,
            "using_mock": isinstance(provider, MockLLMProvider),
            "fallback": provider is self._fallback_provider
            and not (settings.use_mock_llm or settings.llm_provider == "mock"),
            "model_identifier": provider.get_model_identifier(),
        }
        return provider

    def _parse_and_validate_response(self, response_text: str) -> Tuple[str, str, str]:
        try:
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if not json_match:
                raise ValueError(
                    f"No JSON object found in LLM response: {response_text}"
                )

            json_str = json_match.group(0)
            data = json.loads(json_str)

            risk = data.get("risk")
            action = data.get("action")
            rationale = data.get("rationale")

            if not (risk and action and rationale):
                raise ValueError("JSON object is missing required keys.")

            return risk, action, rationale

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(
                f"LLM JSON parsing failed. Error: {e}. Response was: {response_text}"
            )
            raise ValueError(f"LLM JSON parsing failed: {e}")

    async def _run_async_evaluation(
        self, profile: UserViolationProfile, justification: LLMJustification
    ):
        """
        Fire-and-forget evaluation for monitoring.
        Only runs on 10% of traffic to save costs.
        """
        if random.random() > 0.10:
            return

        try:
            metrics = [JsonComplianceMetric(), HallucinationMetric()]
            results = {}

            for metric in metrics:
                response_text = json.dumps(
                    {
                        "risk": justification.risk,
                        "action": justification.action,
                        "rationale": justification.rationale,
                    }
                )

                eval_res = metric.evaluate(response_text, profile)
                results[metric.name] = eval_res["score"]

            if any(score < 1.0 for score in results.values()):
                logger.warning(
                    f"⚠️ Poor LLM Quality Detected for {profile.user.user_id}: {results}"
                )
            else:
                logger.info(f"✅ LLM Quality Check Passed: {results}")

        except Exception as e:
            logger.error(f"Async eval failed: {e}")

    async def generate_user_remediation(
        self, profile: UserViolationProfile
    ) -> LLMJustification:
        email_redacted = self._redact_email(profile.user.email)
        prompt = build_smart_remediation_prompt(profile)

        max_retries = 3

        # Start the timer
        start_time = time.perf_counter()

        for attempt in range(max_retries):
            try:
                response_text = await self.provider.generate(
                    prompt,
                    max_tokens=settings.bedrock_model_max_tokens,
                    profile=profile,
                )

                # Calculate duration
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Log with structured data for OpenSearch
                logger.info(
                    "LLM generation successful",
                    extra={
                        "user_id": profile.user.user_id,
                        "llm_model": self.provider.get_model_identifier(),
                        "duration_ms": round(duration_ms, 2),
                        "attempt": attempt + 1,
                    },
                )

                risk, action, rationale = self._parse_and_validate_response(
                    response_text
                )

                result = LLMJustification(
                    finding_id=profile.finding_id,
                    model_identifier=self.provider.get_model_identifier(),
                    prompt=prompt,
                    response=response_text,
                    risk=risk,
                    action=action,
                    rationale=rationale,
                    email_redacted=email_redacted,
                    generated_at=datetime.utcnow(),
                )

                asyncio.create_task(self._run_async_evaluation(profile, result))

                return result

            except (RuntimeError, ValueError) as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed for user {profile.user.user_id}. "
                    f"Error: {e}"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(attempt + 1)
                else:
                    logger.error(
                        f"All {max_retries} LLM attempts failed for user {profile.user.user_id}. "
                        "Falling back to mock response."
                    )
        return await self._get_mock_justification(profile, prompt, email_redacted)

    async def _get_mock_justification(
        self, profile: UserViolationProfile, prompt: str, email_redacted: str
    ) -> LLMJustification:
        """Creates a generic fallback justification."""

        mock_response_text = await self._fallback_provider.generate(
            prompt, 0, profile=profile
        )

        data = json.loads(mock_response_text)

        return LLMJustification(
            finding_id=profile.finding_id,
            model_identifier=self._fallback_provider.get_model_identifier(),
            prompt=prompt,
            response="FALLBACK: Mock response",
            risk=data["risk"],
            action=data["action"],
            rationale=data["rationale"],
            email_redacted=email_redacted,
            generated_at=datetime.now(timezone.utc),
        )

    def get_status(self) -> dict:
        self.status["model_identifier"] = self.provider.get_model_identifier()
        return self.status

    def _redact_email(self, email: str) -> str:
        parts = str(email).split("@")
        if len(parts) != 2:
            return "***@***"
        local = parts[0]
        domain = parts[1]
        redacted_local = f"{local[0]}***" if len(local) > 1 else "***"
        return f"{redacted_local}@{domain}"


_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
