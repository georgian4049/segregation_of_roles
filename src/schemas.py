"""
Pydantic schemas for API validation (request/response models).
These define the "contract" for our API.
"""
from datetime import datetime
from typing import Any, Literal, List
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from src.models import (
    AssignmentStatus, 
    UserViolationProfile, 
    LLMJustification, 
    ToxicPolicy,
    Finding  , UserRoleState
)



class AssignmentRow(BaseModel):
    """
    Schema for validating a single row from the assignments.csv.
    """
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    user_id: str
    name: str
    email: EmailStr
    department: str
    status: AssignmentStatus
    role: str
    source_system: str
    granted_at_iso: datetime

    @field_validator("granted_at_iso", mode="before")
    @classmethod
    def parse_datetime(cls, v: str | datetime) -> datetime:
        """Parse ISO datetime string."""
        if isinstance(v, datetime):
            return v
        if not isinstance(v, str):
            raise ValueError("datetime must be a string")
        return datetime.fromisoformat(v.replace("Z", "+00:00"))

class IngestResponse(BaseModel):
    """Response from the /ingest endpoint."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    total_assignment_rows: int
    valid_assignment_rows: int
    corrupt_assignment_rows: int
    
    total_policy_rows: int
    valid_policies: int
    corrupt_policies: int
    filtered_policies_single_role: int

    users_processed: int
    active_users: int
    inactive_users: int
    users_with_single_role_filtered: int
    
    total_active_roles: int
    unique_active_roles: int


class FindingResponse(BaseModel):
    """
    A user-centric finding.
    This combines the user's profile with their justification.
    """
    profile: UserViolationProfile
    justification: LLMJustification | None = None

# --- Schemas for Decisions & Evidence ---

class DecisionRequest(BaseModel):
    """Decision submission. This now keys on *user_id*."""
    user_id: str 
    decision: Literal["accept_risk", "revoke_role", "investigate"]
    roles_to_revoke: list[str] = Field(default_factory=list)
    notes: str | None = None
    decided_by: str
    decided_at: datetime = Field(default_factory=datetime.utcnow)

class EvidenceLog(BaseModel):
    """Complete audit evidence package."""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    ingestion_summary: IngestResponse
    policies_used: list[ToxicPolicy]
    policies_hash: str
    findings: list[FindingResponse]
    decisions: list[DecisionRequest]
    metadata: dict[str, Any] = Field(default_factory=dict)

# --- Schemas for Simulation ---

class SimulationRequest(BaseModel):
    """Request payload for role-removal what-if simulation."""
    user_id: str
    role_to_remove: str

class SimulationResponse(BaseModel):
    """Response payload for what-if simulations."""
    user_id: str
    role_removed: str
    resolved: bool
    violations_remaining: List[Finding] # <-- Send back the remaining Finding objects
    message: str
    
    
class RedactedRoleAssignment(BaseModel):
    """Redacted role info for evidence log."""
    role: str
    source_system: str
    granted_at: datetime

class RedactedUserRoleState(BaseModel):
    """Redacted user state for evidence log (GDPR compliance)."""
    user_id: str
    department: str
    status: AssignmentStatus
    active_roles: dict[str, RedactedRoleAssignment]
    source_systems: list[str]
    
    # This model factory converts the full UserRoleState to this redacted one
    @classmethod
    def from_user_role_state(cls, user: UserRoleState):
        redacted_roles = {}
        for role_name, role_obj in user.active_roles.items():
            redacted_roles[role_name] = RedactedRoleAssignment(
                role=role_obj.role,
                source_system=role_obj.source_system,
                granted_at=role_obj.granted_at
            )
        
        return cls(
            user_id=user.user_id,
            department=user.department,
            status=user.status,
            active_roles=redacted_roles,
            source_systems=user.source_systems
        )

class RedactedUserViolationProfile(BaseModel):
    """Redacted violation profile for evidence log."""
    finding_id: str
    user: RedactedUserRoleState # Uses the redacted user model
    violated_policies: list[ToxicPolicy]
    conflicting_role_set: set[str]
    severity: Literal["high"]
    reason: str
    suggested_action: str
    
    @classmethod
    def from_user_violation_profile(cls, profile: UserViolationProfile):
        return cls(
            finding_id=profile.finding_id,
            user=RedactedUserRoleState.from_user_role_state(profile.user),
            violated_policies=profile.violated_policies,
            conflicting_role_set=profile.conflicting_role_set,
            severity=profile.severity,
            reason=profile.reason,
            suggested_action=profile.suggested_action
        )

class EvidenceFindingResponse(BaseModel):
    """A finding response as it appears in the evidence log (redacted)."""
    profile: RedactedUserViolationProfile
    justification: LLMJustification | None = None
    
    @classmethod
    def from_finding_response(cls, response: FindingResponse):
        return cls(
            profile=RedactedUserViolationProfile.from_user_violation_profile(response.profile),
            justification=response.justification
        )