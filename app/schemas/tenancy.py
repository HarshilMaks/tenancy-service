"""
Tenancy Schemas - Pydantic Models for API Validation
====================================================

Pydantic models for request/response validation and OpenAPI documentation.
These models define the contract between the API and clients.

Models align with the application layer DTOs but may have different
field names, validation rules, or transformations.

Author: Platform Engineering Team
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator


class OrganizationBase(BaseModel):
    """Base organization fields shared across schemas."""
    
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Organization name",
        examples=["Acme Corp", "Example LLC"]
    )
    edition: str = Field(
        ...,
        description="Organization edition/tier",
        examples=["free", "essentials", "professional", "enterprise", "unlimited"]
    )
    region: str = Field(
        ...,
        description="Primary data region",
        examples=["us-east-1", "eu-west-1", "ap-southeast-1"]
    )


class CreateOrganizationRequest(OrganizationBase):
    """Request schema for creating organizations."""
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Acme Corporation",
                "edition": "professional", 
                "region": "us-east-1"
            }
        }
    )


class OrganizationResponse(OrganizationBase):
    """Response schema for organization details."""
    
    id: UUID = Field(
        ...,
        description="Unique organization identifier"
    )
    status: str = Field(
        ...,
        description="Current organization status",
        examples=["trial", "active", "suspended", "cancelled"]
    )
    created_at: datetime = Field(
        ...,
        description="Organization creation timestamp"
    )
    updated_at: datetime = Field(
        ...,
        description="Last update timestamp"
    )
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Acme Corporation",
                "edition": "professional",
                "region": "us-east-1",
                "status": "active",
                "created_at": "2024-01-01T12:00:00Z",
                "updated_at": "2024-01-01T12:00:00Z"
            }
        }
    )


class SuspendOrganizationRequest(BaseModel):
    """Request schema for suspending organizations."""
    
    reason: str = Field(
        ...,
        description="Suspension reason",
        examples=["payment_failure", "policy_violation", "security_concern"]
    )
    grace_period_hours: Optional[int] = Field(
        None,
        ge=0,
        le=720,  # 30 days max
        description="Grace period before full suspension"
    )
    notes: Optional[str] = Field(
        None,
        max_length=1000,
        description="Additional suspension notes"
    )


class PolicyCheckRequest(BaseModel):
    """Request schema for policy checks."""
    
    action: str = Field(
        ...,
        description="Action to check",
        examples=["create_workspace", "invite_user", "export_data"]
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context for policy check"
    )


class PolicyCheckResponse(BaseModel):
    """Response schema for policy checks."""
    
    allowed: bool = Field(
        ...,
        description="Whether action is allowed"
    )
    decision: str = Field(
        ...,
        description="Policy decision code",
        examples=["allow", "deny", "conditional"]
    )
    violations: List[str] = Field(
        default_factory=list,
        description="List of policy violations if denied"
    )
    required_upgrade: Optional[str] = Field(
        None,
        description="Required edition upgrade if applicable"
    )


class ErrorResponse(BaseModel):
    """Standard error response schema."""
    
    error: str = Field(
        ...,
        description="Error type or code"
    )
    message: str = Field(
        ...,
        description="Human-readable error message"
    )
    details: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional error details"
    )
    correlation_id: Optional[str] = Field(
        None,
        description="Request correlation ID for tracing"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "VALIDATION_ERROR",
                "message": "Invalid organization name",
                "details": {"field": "name", "constraint": "min_length"},
                "correlation_id": "req_123e4567"
            }
        }
    )