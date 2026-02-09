"""Compliance endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List

from infrastructure.persistence.tenant_repository import OrganizationRepository, OrganizationNotFoundError
from app.dependencies.providers import get_organization_repository

router = APIRouter(prefix="/api/v1/compliance", tags=["Compliance"])

# Compliance standards available
COMPLIANCE_STANDARDS = ["HIPAA", "SOC2", "GDPR", "PCI_DSS"]


class ComplianceRequirement(BaseModel):
    standard: str
    enabled: bool
    description: str


class ComplianceResponse(BaseModel):
    org_id: str
    requirements: List[ComplianceRequirement]


@router.get("/{org_id}", response_model=ComplianceResponse)
async def get_compliance(
    org_id: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Get compliance requirements."""
    try:
        org = repo.get_by_org_id(org_id)
        
        # Get enabled compliance standards from org metadata
        enabled_standards = org.metadata.get("compliance_standards", []) if org.metadata else []
        
        requirements = [
            {
                "standard": standard,
                "enabled": standard in enabled_standards,
                "description": f"{standard} compliance"
            }
            for standard in COMPLIANCE_STANDARDS
        ]
        
        return {
            "org_id": org.org_id,
            "requirements": requirements,
        }
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )


@router.post("/{org_id}/{standard}", response_model=dict)
async def enable_compliance(
    org_id: str,
    standard: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Enable compliance standard."""
    if standard not in COMPLIANCE_STANDARDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid compliance standard: {standard}"
        )
    
    try:
        org = repo.get_by_org_id(org_id)
        
        if not org.metadata:
            org.metadata = {}
        
        if "compliance_standards" not in org.metadata:
            org.metadata["compliance_standards"] = []
        
        if standard not in org.metadata["compliance_standards"]:
            org.metadata["compliance_standards"].append(standard)
        
        repo.save(org)
        
        return {"org_id": org_id, "standard": standard, "status": "enabled"}
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )


@router.delete("/{org_id}/{standard}", response_model=dict)
async def disable_compliance(
    org_id: str,
    standard: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Disable compliance standard."""
    if standard not in COMPLIANCE_STANDARDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid compliance standard: {standard}"
        )
    
    try:
        org = repo.get_by_org_id(org_id)
        
        if org.metadata and "compliance_standards" in org.metadata:
            if standard in org.metadata["compliance_standards"]:
                org.metadata["compliance_standards"].remove(standard)
        
        repo.save(org)
        
        return {"org_id": org_id, "standard": standard, "status": "disabled"}
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )
