"""
Core domain models for the application.
These models represent the internal business logic and data structures.
"""
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from logging import getLogger
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

logger = getLogger(__name__)

class AssignmentStatus(StrEnum):
    """Assignment status enum."""
    ACTIVE = "active"
    INACTIVE = "inactive"


class Assignment(BaseModel):
    """User role assignment from CSV."""
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
        return datetime.fromisoformat(v.replace("Z", "+00:00"))


class ToxicPolicy(BaseModel):
    """Toxic combination policy."""
    model_config = ConfigDict(str_strip_whitespace=True)

    policy_id: str
    description: str
    roles: set[str] = Field(min_length=2) 


class RoleAssignment(BaseModel):
    """Individual role with temporal and source information."""
    role: str
    source_system: str
    granted_at: datetime


class UserRoleState(BaseModel):
    """Aggregated user state with temporal role resolution."""
    user_id: str
    name: str
    email: EmailStr
    department: str
    status: AssignmentStatus 
    
    active_roles: dict[str, RoleAssignment] = Field(default_factory=dict)
    
    source_systems: list[str] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Finding(BaseModel):
    """
    Internal finding for a *single* policy violation.
    This is created by the DetectionEngine.
    """
    finding_id: str
    user_id: str
    policy_id: str
    roles_matched: dict[str, str] 
    severity: Literal["high"] = "high"
    reason: str
    suggested_action: str = "revoke one role"


class UserViolationProfile(BaseModel):
    """
    A model that groups all violations for a *single user*.
    """
    finding_id: str
    user: UserRoleState
    violated_policies: list[ToxicPolicy]
    conflicting_role_set: set[str]
    
    severity: Literal["high"] = "high"
    reason: str
    suggested_action: str = "revoke one role"

    model_config = ConfigDict(arbitrary_types_allowed=True)


class LLMJustification(BaseModel):
    """LLM-generated justification for a user's *entire profile*."""
    finding_id: str 
    model_identifier: str
    prompt: str
    response: str
    risk: str
    action: str
    rationale: str
    email_redacted: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    
    
class JustifyRequest(BaseModel):
    """
    This is the Pydantic model for the /justify-finding endpoint.
    It was defined in your routes.py, but belongs in models.py
    or schemas.py. Let's keep it with the other models.
    """
    finding: Finding
    user_state: UserRoleState
    policy: ToxicPolicy