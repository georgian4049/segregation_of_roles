import logging
import uuid  
from src.models import ToxicPolicy, UserRoleState, UserViolationProfile
from src.services.policy_store import PolicyStore

logger = logging.getLogger(__name__)


class DetectionEngine:
    """
    Detects toxic role combinations based on policies.
    Aggregates *all* violations for a single user into one profile.
    """

    def __init__(self, policy_store: PolicyStore):
        self.policy_store = policy_store

    def detect_violations(
        self, user_states: dict[str, UserRoleState]
    ) -> dict[str, UserViolationProfile]:
        """
        Detect all toxic combinations across all active, multi-role users.
        """
        violation_profiles: dict[str, UserViolationProfile] = {}
        policies = self.policy_store.get_all_policies()
        
        if not policies:
            logger.warning("No policies loaded - detection skipped")
            return {}

        logger.info(
            f"Running detection: {len(user_states)} users, {len(policies)} policies"
        )

        for user_id, user_state in user_states.items():
            user_roles_set = set(user_state.active_roles.keys())
            
            violated_policies: list[ToxicPolicy] = []
            
            for policy in policies:
                if policy.roles.issubset(user_roles_set):
                    violated_policies.append(policy)

            if violated_policies:
                # 1. Get all conflicting roles and policy IDs
                all_conflicting_roles = set()
                policy_ids = []
                for p in violated_policies:
                    all_conflicting_roles.update(p.roles)
                    policy_ids.append(p.policy_id)

                # 2. Generate a dynamic reason (as required by the spec)
                reason = f"User violates {len(policy_ids)} policies: {', '.join(sorted(policy_ids))}"
                
                # 3. Generate a USER-CENTRIC finding_id
                finding_id = self._generate_finding_id(user_id)
                
                # 4. Create the single profile for this user
                violation_profiles[user_id] = UserViolationProfile(
                    finding_id=finding_id,
                    user=user_state,
                    violated_policies=violated_policies,
                    conflicting_role_set=all_conflicting_roles,
                    severity="high",
                    suggested_action="revoke one role",
                    reason=reason
                )

        logger.info(f"Detection complete: {len(violation_profiles)} users with violations found")
        return violation_profiles
    
    def _generate_finding_id(self, user_id: str) -> str:
        """
        Generate deterministic, USER-CENTRIC finding ID.
        """
        # Using a fixed namespace for reproducible IDs
        namespace = uuid.UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479")
        unique_str = f"user:{user_id}"
        finding_uuid = uuid.uuid5(namespace, unique_str)
        return f"FINDING-{str(finding_uuid)[:12].upper()}"