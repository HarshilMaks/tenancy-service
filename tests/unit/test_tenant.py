from uuid import uuid4
from app.db.models.domain_models import Organization, OrganizationStatus, Edition


def test_active_tenant_can_create_ticket():
    tenant = Organization(
        id=uuid4(),
        org_id="ORG-TEST",
        name="Test Org",
        normalized_name="test org",
        status=OrganizationStatus.ACTIVE,
        edition=Edition.FREE,
    )
    assert tenant.can_perform_operations() is True


def test_suspended_tenant_cannot_create_ticket():
    tenant = Organization(
        id=uuid4(),
        org_id="ORG-TEST2",
        name="Test Org 2",
        normalized_name="test org 2",
        status=OrganizationStatus.SUSPENDED,
        edition=Edition.FREE,
    )
    assert tenant.can_perform_operations() is False