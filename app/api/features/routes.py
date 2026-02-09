"""Feature gating endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Dict, List

from infrastructure.persistence.tenant_repository import OrganizationRepository, OrganizationNotFoundError
from app.dependencies.providers import get_organization_repository

router = APIRouter(prefix="/api/v1/features", tags=["Features"])

# Feature matrix by edition
FEATURE_MATRIX = {
    "free": {
        "api_access": False,
        "custom_branding": False,
        "sso": False,
        "advanced_analytics": False,
        "basic_support": True,
    },
    "essentials": {
        "api_access": True,
        "custom_branding": False,
        "sso": False,
        "advanced_analytics": False,
        "basic_support": True,
    },
    "professional": {
        "api_access": True,
        "custom_branding": True,
        "sso": False,
        "advanced_analytics": True,
        "basic_support": True,
    },
    "enterprise": {
        "api_access": True,
        "custom_branding": True,
        "sso": True,
        "advanced_analytics": True,
        "basic_support": True,
    },
    "unlimited": {
        "api_access": True,
        "custom_branding": True,
        "sso": True,
        "advanced_analytics": True,
        "basic_support": True,
    },
}


class FeatureFlag(BaseModel):
    name: str
    enabled: bool
    description: str


class FeatureGateResponse(BaseModel):
    org_id: str
    edition: str
    features: Dict[str, bool]


@router.get("/{org_id}", response_model=FeatureGateResponse)
async def get_features(
    org_id: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Get available features for organization."""
    try:
        org = repo.get_by_org_id(org_id)
        
        edition = org.edition.lower() if hasattr(org.edition, 'lower') else str(org.edition).lower()
        features = FEATURE_MATRIX.get(edition, {})
        
        return {
            "org_id": org.org_id,
            "edition": edition,
            "features": features,
        }
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )


@router.get("/{org_id}/{feature_name}", response_model=dict)
async def check_feature(
    org_id: str,
    feature_name: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Check if feature is enabled."""
    try:
        org = repo.get_by_org_id(org_id)
        
        edition = org.edition.lower() if hasattr(org.edition, 'lower') else str(org.edition).lower()
        features = FEATURE_MATRIX.get(edition, {})
        enabled = features.get(feature_name, False)
        
        return {"org_id": org_id, "feature": feature_name, "enabled": enabled}
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )


@router.get("", response_model=List[FeatureFlag])
async def list_all_features():
    """List all available features."""
    all_features = set()
    for features in FEATURE_MATRIX.values():
        all_features.update(features.keys())
    
    return [
        {"name": feature, "enabled": True, "description": f"{feature.replace('_', ' ').title()}"}
        for feature in sorted(all_features)
    ]
