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
    Finding,
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
    violations_remaining: List[Finding]  # <-- Send back the remaining Finding objects
    message: str
