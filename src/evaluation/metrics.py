"""
Evaluation metrics for LLM responses.
"""
import json
import logging
from typing import Dict, Any
from src.models import UserViolationProfile

logger = logging.getLogger(__name__)


class EvalMetric:
    def __init__(self, name: str):
        self.name = name

    def evaluate(
        self, llm_response: str, profile: UserViolationProfile
    ) -> Dict[str, Any]:
        """
        Returns:
            {
                "score": float (0.0 to 1.0),
                "reason": str,
                "metadata": dict
            }
        """
        raise NotImplementedError


class JsonComplianceMetric(EvalMetric):
    """Checks if the output is valid JSON and has required keys."""

    def __init__(self):
        super().__init__("json_compliance")
        self.required_keys = {"risk", "action", "rationale"}

    def evaluate(
        self, llm_response: str, profile: UserViolationProfile
    ) -> Dict[str, Any]:
        try:
            data = json.loads(llm_response)
            missing = self.required_keys - data.keys()
            if missing:
                return {
                    "score": 0.0,
                    "reason": f"Missing keys: {missing}",
                    "metadata": {},
                }
            return {"score": 1.0, "reason": "Valid JSON schema", "metadata": {}}
        except json.JSONDecodeError:
            return {"score": 0.0, "reason": "Invalid JSON syntax", "metadata": {}}


class HallucinationMetric(EvalMetric):
    """
    Checks if the suggested 'action' refers to a role that the user ACTUALLY has.
    This prevents the LLM from inventing roles to revoke.
    """

    def __init__(self):
        super().__init__("hallucination_check")

    def evaluate(
        self, llm_response: str, profile: UserViolationProfile
    ) -> Dict[str, Any]:
        try:
            data = json.loads(llm_response)
            action_text = data.get("action", "").lower()

            # Get list of user's actual roles (normalized to lowercase)
            user_roles = {r.lower() for r in profile.user.active_roles.keys()}

            # Heuristic: Check if any of the user's roles appear in the action text
            found_role = any(role in action_text for role in user_roles)

            if found_role:
                return {
                    "score": 1.0,
                    "reason": "Action references a real user role",
                    "metadata": {"matched_roles": list(user_roles)},
                }
            else:
                return {
                    "score": 0.0,
                    "reason": f"Action '{action_text}' does not mention any known user roles: {user_roles}",
                    "metadata": {"user_roles": list(user_roles)},
                }
        except json.JSONDecodeError:
            return {"score": 0.0, "reason": "Skipped (Invalid JSON)", "metadata": {}}


class RiskKeywordMetric(EvalMetric):
    """
    Simple heuristic to ensure the 'risk' field contains serious terminology.
    """

    def __init__(self):
        super().__init__("risk_content")
        self.keywords = [
            "fraud",
            "unauthorized",
            "conflict",
            "access",
            "compliance",
            "violation",
        ]

    def evaluate(
        self, llm_response: str, profile: UserViolationProfile
    ) -> Dict[str, Any]:
        try:
            data = json.loads(llm_response)
            risk_text = data.get("risk", "").lower()

            found_keywords = [k for k in self.keywords if k in risk_text]

            if found_keywords:
                return {
                    "score": 1.0,
                    "reason": f"Found keywords: {found_keywords}",
                    "metadata": {"keywords": found_keywords},
                }
            return {
                "score": 0.5,
                "reason": "No specific risk keywords found (weak description?)",
                "metadata": {},
            }  # 0.5 penalization, not failure
        except Exception:
            logger.error("Evaluation error")
            raise "Evalution error"
