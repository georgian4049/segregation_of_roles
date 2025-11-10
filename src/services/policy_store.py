"""
Policy store for managing toxic combination policies.
"""
import logging
from src.models import ToxicPolicy

logger = logging.getLogger(__name__)

class PolicyStore:
    """
    A simple, in-memory store for toxic combination policies.
    This is treated as a singleton by the FastAPI routes.
    """
    def __init__(self):
        self._policies: dict[str, ToxicPolicy] = {}
        logger.info("PolicyStore initialized.")

    def update_policies(self, policies: list[ToxicPolicy]):
        """
        Replaces all policies in the store with a new list.
        """
        self._policies = {p.policy_id: p for p in policies}
        logger.info(f"Policy store updated with {len(self._policies)} policies.")

    def get_policy(self, policy_id: str) -> ToxicPolicy | None:
        """Get a specific policy by ID."""
        return self._policies.get(policy_id)

    def get_all_policies(self) -> list[ToxicPolicy]:
        """Get all active policies."""
        return list(self._policies.values())