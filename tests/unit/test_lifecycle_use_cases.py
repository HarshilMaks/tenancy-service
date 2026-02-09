"""
Property-Based Tests for Lifecycle Use Cases
=============================================

Tests for ActivateOrganizationUseCase, ResumeOrganizationUseCase,
TerminateOrganizationUseCase, and DeleteOrganizationUseCase.

Uses hypothesis for property-based testing to verify correctness
across a wide range of inputs.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock
from hypothesis import given, strategies as st, assume
from uuid import uuid4

# Import use cases
from app.business.use_cases.activate_tenant import (
    ActivateOrganizationUseCase,
    ActivateOrganizationRequest,
    ActivateOrganizationError,
)
from app.business.use_cases.resume_tenant import (
    ResumeOrganizationUseCase,
    ResumeOrganizationRequest,
    ResumeOrganizationError,
)
from app.business.use_cases.terminate_tenant import (
    TerminateOrganizationUseCase,
    TerminateOrganizationRequest,
    TerminateOrganizationError,
)
from app.business.use_cases.delete_tenant import (
    DeleteOrganizationUseCase,
    DeleteOrganizationRequest,
    DeleteOrganizationError,
)

# Import domain models
from app.db.models.domain_models import (
    Organization,
    OrganizationStatus,
    Edition,
    SuspensionInfo,
    SuspensionReason,
    SuspensionSeverity,
)

# Import events
from app.business.events.tenant_events import (
    OrganizationActivatedEvent,
    OrganizationResumedEvent,
    OrganizationTerminatedEvent,
)


# =============================================================================
# FIXTURES AND HELPERS
# =============================================================================

def create_mock_organization(
    org_id: str = "ORG-TEST123",
    status: OrganizationStatus = OrganizationStatus.PROVISIONING,
    edition: Edition = Edition.PROFESSIONAL,
) -> Organization:
    """Create a mock organization for testing."""
    return Organization(
        id=uuid4(),
        org_id=org_id,
        name=f"Test Org {org_id}",
        normalized_name=f"test org {org_id}".lower(),
        status=status,
        edition=edition,
    )


def create_mock_repository(org: Organization = None) -> Mock:
    """Create a mock repository."""
    repo = Mock()
    if org:
        repo.get_by_org_id.return_value = org
    else:
        repo.get_by_org_id.return_value = None
    repo.save.return_value = org
    repo.delete.return_value = None
    return repo


def create_mock_event_publisher() -> Mock:
    """Create a mock event publisher."""
    publisher = Mock()
    publisher.publish.return_value = None
    publisher.publish_batch.return_value = None
    return publisher


# =============================================================================
# ACTIVATE ORGANIZATION USE CASE TESTS
# =============================================================================

class TestActivateOrganizationUseCase:
    """Tests for ActivateOrganizationUseCase."""
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
        activated_by=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
    )
    def test_activate_from_provisioning_transitions_to_active(self, org_id, activated_by):
        """
        Property 1: Activate Transitions to Active
        **Validates: Requirements 1.1, 1.2, 1.6**
        
        For any organization in PROVISIONING state, executing ActivateOrganizationUseCase
        should transition the organization to ACTIVE status and persist the change.
        """
        # Setup
        org = create_mock_organization(org_id=org_id, status=OrganizationStatus.PROVISIONING)
        repo = create_mock_repository(org)
        publisher = create_mock_event_publisher()
        use_case = ActivateOrganizationUseCase(repo, publisher)
        
        request = ActivateOrganizationRequest(
            org_id=org_id,
            activated_by=activated_by,
        )
        
        # Execute
        response = use_case.execute(request)
        
        # Verify
        assert response.success is True
        assert response.org_id == org_id
        assert response.new_status == OrganizationStatus.ACTIVE.value
        assert response.activated_at is not None
        assert response.error_code is None
        
        # Verify persistence
        repo.save.assert_called_once()
        saved_org = repo.save.call_args[0][0]
        assert saved_org.status == OrganizationStatus.ACTIVE
        assert saved_org.activated_at is not None
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_activate_from_trial_transitions_to_active(self, org_id):
        """
        Property 1: Activate Transitions to Active (from TRIAL)
        **Validates: Requirements 1.1, 1.2, 1.6**
        
        For any organization in TRIAL state, executing ActivateOrganizationUseCase
        should transition the organization to ACTIVE status.
        """
        # Setup
        org = create_mock_organization(org_id=org_id, status=OrganizationStatus.TRIAL)
        repo = create_mock_repository(org)
        publisher = create_mock_event_publisher()
        use_case = ActivateOrganizationUseCase(repo, publisher)
        
        request = ActivateOrganizationRequest(org_id=org_id)
        
        # Execute
        response = use_case.execute(request)
        
        # Verify
        assert response.success is True
        assert response.new_status == OrganizationStatus.ACTIVE.value
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_activate_publishes_event(self, org_id):
        """
        Property 2: Activate Publishes Event
        **Validates: Requirements 1.5**
        
        For any organization successfully activated, an OrganizationActivatedEvent
        should be published containing the org_id, edition, and activated_from status.
        """
        # Setup
        org = create_mock_organization(org_id=org_id, status=OrganizationStatus.PROVISIONING)
        repo = create_mock_repository(org)
        publisher = create_mock_event_publisher()
        use_case = ActivateOrganizationUseCase(repo, publisher)
        
        request = ActivateOrganizationRequest(org_id=org_id)
        
        # Execute
        response = use_case.execute(request)
        
        # Verify event published
        assert response.success is True
        publisher.publish.assert_called_once()
        
        event = publisher.publish.call_args[0][0]
        assert isinstance(event, OrganizationActivatedEvent)
        assert event.org_id == org_id
        assert event.edition == org.edition.value
        assert event.activated_from == OrganizationStatus.PROVISIONING.value
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_activate_invalid_state_returns_error(self, org_id):
        """
        Property 10: Invalid State Transitions Rejected
        **Validates: Requirements 1.3**
        
        For any organization in an invalid state for activation (except ACTIVE which is idempotent),
        the use case should return INVALID_STATE_TRANSITION error without modifying the organization.
        """
        # Setup - try to activate from PENDING_TERMINATION state (invalid)
        org = create_mock_organization(org_id=org_id, status=OrganizationStatus.PENDING_TERMINATION)
        repo = create_mock_repository(org)
        publisher = create_mock_event_publisher()
        use_case = ActivateOrganizationUseCase(repo, publisher)
        
        request = ActivateOrganizationRequest(org_id=org_id)
        
        # Execute
        response = use_case.execute(request)
        
        # Verify error
        assert response.success is False
        assert response.error_code == ActivateOrganizationError.INVALID_STATE_TRANSITION
        assert len(response.errors) > 0
        
        # Verify no persistence
        repo.save.assert_not_called()
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_activate_already_active_is_idempotent(self, org_id):
        """
        Property 11: Idempotent Activation
        **Validates: Requirements 1.4**
        
        Activating an already-active organization should succeed without error.
        """
        # Setup - organization already active
        org = create_mock_organization(org_id=org_id, status=OrganizationStatus.ACTIVE)
        repo = create_mock_repository(org)
        publisher = create_mock_event_publisher()
        use_case = ActivateOrganizationUseCase(repo, publisher)
        
        request = ActivateOrganizationRequest(org_id=org_id)
        
        # Execute
        response = use_case.execute(request)
        
        # Verify success (idempotent)
        assert response.success is True
        assert response.new_status == OrganizationStatus.ACTIVE.value
        
        # Verify no persistence (already active)
        repo.save.assert_not_called()
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_activate_not_found_returns_error(self, org_id):
        """
        Property 11: Not Found Returns Error
        **Validates: Requirements 1.4**
        
        For any non-existent org_id, the use case should return ORGANIZATION_NOT_FOUND
        error without attempting state transition.
        """
        # Setup
        repo = create_mock_repository(None)  # No organization found
        publisher = create_mock_event_publisher()
        use_case = ActivateOrganizationUseCase(repo, publisher)
        
        request = ActivateOrganizationRequest(org_id=org_id)
        
        # Execute
        response = use_case.execute(request)
        
        # Verify error
        assert response.success is False
        assert response.error_code == ActivateOrganizationError.ORGANIZATION_NOT_FOUND
        assert len(response.errors) > 0


# =============================================================================
# RESUME ORGANIZATION USE CASE TESTS
# =============================================================================

class TestResumeOrganizationUseCase:
    """Tests for ResumeOrganizationUseCase."""
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_resume_from_suspended_transitions_to_active(self, org_id):
        """
        Property 3: Resume Clears Suspension
        **Validates: Requirements 2.1, 2.4**
        
        For any suspended organization, executing ResumeOrganizationUseCase should
        clear the suspension_info field and transition to ACTIVE status.
        """
        # Setup
        org = create_mock_organization(org_id=org_id, status=OrganizationStatus.SUSPENDED)
        org.suspension_info = SuspensionInfo(
            reason=SuspensionReason.PAYMENT_FAILED,
            severity=SuspensionSeverity.SOFT,
            description="Payment failed",
            suspended_at=datetime.now(timezone.utc),
        )
        repo = create_mock_repository(org)
        publisher = create_mock_event_publisher()
        use_case = ResumeOrganizationUseCase(repo, publisher)
        
        request = ResumeOrganizationRequest(org_id=org_id)
        
        # Execute
        response = use_case.execute(request)
        
        # Verify
        assert response.success is True
        assert response.org_id == org_id
        assert response.new_status == OrganizationStatus.ACTIVE.value
        assert response.resumed_at is not None
        
        # Verify suspension_info cleared
        repo.save.assert_called_once()
        saved_org = repo.save.call_args[0][0]
        assert saved_org.status == OrganizationStatus.ACTIVE
        assert saved_org.suspension_info is None
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_resume_publishes_event(self, org_id):
        """
        Property 4: Resume Publishes Event
        **Validates: Requirements 2.5**
        
        For any organization successfully resumed, an OrganizationResumedEvent
        should be published containing the org_id and resumed_at timestamp.
        """
        # Setup
        org = create_mock_organization(org_id=org_id, status=OrganizationStatus.SUSPENDED)
        org.suspension_info = SuspensionInfo(
            reason=SuspensionReason.PAYMENT_FAILED,
            severity=SuspensionSeverity.SOFT,
            description="Payment failed",
            suspended_at=datetime.now(timezone.utc),
        )
        repo = create_mock_repository(org)
        publisher = create_mock_event_publisher()
        use_case = ResumeOrganizationUseCase(repo, publisher)
        
        request = ResumeOrganizationRequest(org_id=org_id)
        
        # Execute
        response = use_case.execute(request)
        
        # Verify event published
        assert response.success is True
        publisher.publish.assert_called_once()
        
        event = publisher.publish.call_args[0][0]
        assert isinstance(event, OrganizationResumedEvent)
        assert event.org_id == org_id
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_resume_invalid_state_returns_error(self, org_id):
        """
        Property 10: Invalid State Transitions Rejected
        **Validates: Requirements 2.2**
        
        For any organization in an invalid state for resume, the use case
        should return INVALID_STATE_TRANSITION error.
        """
        # Setup - try to resume from ACTIVE state (invalid)
        org = create_mock_organization(org_id=org_id, status=OrganizationStatus.ACTIVE)
        repo = create_mock_repository(org)
        publisher = create_mock_event_publisher()
        use_case = ResumeOrganizationUseCase(repo, publisher)
        
        request = ResumeOrganizationRequest(org_id=org_id)
        
        # Execute
        response = use_case.execute(request)
        
        # Verify error
        assert response.success is False
        assert response.error_code == ResumeOrganizationError.INVALID_STATE_TRANSITION
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_resume_not_found_returns_error(self, org_id):
        """
        Property 11: Not Found Returns Error
        **Validates: Requirements 2.3**
        
        For any non-existent org_id, the use case should return ORGANIZATION_NOT_FOUND error.
        """
        # Setup
        repo = create_mock_repository(None)
        publisher = create_mock_event_publisher()
        use_case = ResumeOrganizationUseCase(repo, publisher)
        
        request = ResumeOrganizationRequest(org_id=org_id)
        
        # Execute
        response = use_case.execute(request)
        
        # Verify error
        assert response.success is False
        assert response.error_code == ResumeOrganizationError.ORGANIZATION_NOT_FOUND


# =============================================================================
# TERMINATE ORGANIZATION USE CASE TESTS
# =============================================================================

class TestTerminateOrganizationUseCase:
    """Tests for TerminateOrganizationUseCase."""
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
        retention_days=st.integers(min_value=1, max_value=365),
    )
    def test_terminate_sets_retention_period(self, org_id, retention_days):
        """
        Property 5: Terminate Sets Retention
        **Validates: Requirements 3.4**
        
        For any organization terminated with a data_retention_days parameter,
        the data_retention_until field should be set to current_time + data_retention_days.
        """
        # Setup
        org = create_mock_organization(org_id=org_id, status=OrganizationStatus.ACTIVE)
        repo = create_mock_repository(org)
        publisher = create_mock_event_publisher()
        use_case = TerminateOrganizationUseCase(repo, publisher)
        
        before_time = datetime.now(timezone.utc)
        request = TerminateOrganizationRequest(
            org_id=org_id,
            reason="Customer requested",
            data_retention_days=retention_days,
        )
        
        # Execute
        response = use_case.execute(request)
        after_time = datetime.now(timezone.utc)
        
        # Verify
        assert response.success is True
        assert response.data_retention_until is not None
        
        # Verify retention period is approximately correct
        expected_min = before_time + timedelta(days=retention_days)
        expected_max = after_time + timedelta(days=retention_days)
        assert expected_min <= response.data_retention_until <= expected_max
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_terminate_default_retention_90_days(self, org_id):
        """
        Property 6: Terminate Default Retention
        **Validates: Requirements 3.5**
        
        For any organization terminated without a data_retention_days parameter,
        the data_retention_until field should be set to current_time + 90 days.
        """
        # Setup
        org = create_mock_organization(org_id=org_id, status=OrganizationStatus.ACTIVE)
        repo = create_mock_repository(org)
        publisher = create_mock_event_publisher()
        use_case = TerminateOrganizationUseCase(repo, publisher)
        
        before_time = datetime.now(timezone.utc)
        request = TerminateOrganizationRequest(
            org_id=org_id,
            reason="Customer requested",
            # data_retention_days not specified, should default to 90
        )
        
        # Execute
        response = use_case.execute(request)
        after_time = datetime.now(timezone.utc)
        
        # Verify
        assert response.success is True
        assert response.data_retention_until is not None
        
        # Verify default retention is 90 days
        expected_min = before_time + timedelta(days=90)
        expected_max = after_time + timedelta(days=90)
        assert expected_min <= response.data_retention_until <= expected_max
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_terminate_publishes_event(self, org_id):
        """
        Property 7: Terminate Publishes Event
        **Validates: Requirements 3.8**
        
        For any organization successfully terminated, an OrganizationTerminatedEvent
        should be published containing org_id, terminated_at, and termination_reason.
        """
        # Setup
        org = create_mock_organization(org_id=org_id, status=OrganizationStatus.ACTIVE)
        repo = create_mock_repository(org)
        publisher = create_mock_event_publisher()
        use_case = TerminateOrganizationUseCase(repo, publisher)
        
        reason = "Customer requested termination"
        request = TerminateOrganizationRequest(
            org_id=org_id,
            reason=reason,
        )
        
        # Execute
        response = use_case.execute(request)
        
        # Verify event published
        assert response.success is True
        publisher.publish.assert_called_once()
        
        event = publisher.publish.call_args[0][0]
        assert isinstance(event, OrganizationTerminatedEvent)
        assert event.org_id == org_id
        assert event.reason == reason
        assert event.data_retention_until is not None
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_terminate_invalid_state_returns_error(self, org_id):
        """
        Property 10: Invalid State Transitions Rejected
        **Validates: Requirements 3.3**
        
        For any organization in an invalid state for termination, the use case
        should return INVALID_STATE_TRANSITION error.
        """
        # Setup - try to terminate from TERMINATED state (invalid)
        org = create_mock_organization(org_id=org_id, status=OrganizationStatus.TERMINATED)
        org.terminated_at = datetime.now(timezone.utc)
        org.data_retention_until = datetime.now(timezone.utc) + timedelta(days=90)
        repo = create_mock_repository(org)
        publisher = create_mock_event_publisher()
        use_case = TerminateOrganizationUseCase(repo, publisher)
        
        request = TerminateOrganizationRequest(
            org_id=org_id,
            reason="Test",
        )
        
        # Execute
        response = use_case.execute(request)
        
        # Verify error
        assert response.success is False
        assert response.error_code == TerminateOrganizationError.INVALID_STATE_TRANSITION
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_terminate_not_found_returns_error(self, org_id):
        """
        Property 11: Not Found Returns Error
        **Validates: Requirements 3.2**
        
        For any non-existent org_id, the use case should return ORGANIZATION_NOT_FOUND error.
        """
        # Setup
        repo = create_mock_repository(None)
        publisher = create_mock_event_publisher()
        use_case = TerminateOrganizationUseCase(repo, publisher)
        
        request = TerminateOrganizationRequest(
            org_id=org_id,
            reason="Test",
        )
        
        # Execute
        response = use_case.execute(request)
        
        # Verify error
        assert response.success is False
        assert response.error_code == TerminateOrganizationError.ORGANIZATION_NOT_FOUND


# =============================================================================
# DELETE ORGANIZATION USE CASE TESTS
# =============================================================================

class TestDeleteOrganizationUseCase:
    """Tests for DeleteOrganizationUseCase."""
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_delete_requires_retention_expiry(self, org_id):
        """
        Property 8: Delete Requires Retention Expiry
        **Validates: Requirements 4.3**
        
        For any terminated organization still within the retention period,
        executing DeleteOrganizationUseCase should return RETENTION_PERIOD_NOT_EXPIRED error.
        """
        # Setup - organization still within retention period
        org = create_mock_organization(org_id=org_id, status=OrganizationStatus.TERMINATED)
        org.terminated_at = datetime.now(timezone.utc) - timedelta(days=30)
        org.data_retention_until = datetime.now(timezone.utc) + timedelta(days=60)  # Still in retention
        repo = create_mock_repository(org)
        publisher = create_mock_event_publisher()
        use_case = DeleteOrganizationUseCase(repo, publisher)
        
        request = DeleteOrganizationRequest(org_id=org_id)
        
        # Execute
        response = use_case.execute(request)
        
        # Verify error
        assert response.success is False
        assert response.error_code == DeleteOrganizationError.RETENTION_PERIOD_NOT_EXPIRED
        assert len(response.errors) > 0
        
        # Verify no deletion
        repo.delete.assert_not_called()
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_delete_publishes_event(self, org_id):
        """
        Property 9: Delete Publishes Event
        **Validates: Requirements 4.5**
        
        For any organization successfully deleted, an OrganizationDeletedEvent
        should be published containing org_id and deleted_at timestamp.
        """
        # Setup - organization past retention period
        org = create_mock_organization(org_id=org_id, status=OrganizationStatus.TERMINATED)
        org.terminated_at = datetime.now(timezone.utc) - timedelta(days=100)
        org.data_retention_until = datetime.now(timezone.utc) - timedelta(days=10)  # Past retention
        repo = create_mock_repository(org)
        publisher = create_mock_event_publisher()
        use_case = DeleteOrganizationUseCase(repo, publisher)
        
        request = DeleteOrganizationRequest(org_id=org_id)
        
        # Execute
        response = use_case.execute(request)
        
        # Verify success
        assert response.success is True
        
        # Verify event published
        publisher.publish.assert_called_once()
        event = publisher.publish.call_args[0][0]
        assert event.org_id == org_id
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_delete_invalid_state_returns_error(self, org_id):
        """
        Property 10: Invalid State Transitions Rejected
        **Validates: Requirements 4.2**
        
        For any organization in an invalid state for deletion, the use case
        should return INVALID_STATE_TRANSITION error.
        """
        # Setup - try to delete from ACTIVE state (invalid)
        org = create_mock_organization(org_id=org_id, status=OrganizationStatus.ACTIVE)
        repo = create_mock_repository(org)
        publisher = create_mock_event_publisher()
        use_case = DeleteOrganizationUseCase(repo, publisher)
        
        request = DeleteOrganizationRequest(org_id=org_id)
        
        # Execute
        response = use_case.execute(request)
        
        # Verify error
        assert response.success is False
        assert response.error_code == DeleteOrganizationError.INVALID_STATE_TRANSITION
        
        # Verify no deletion
        repo.delete.assert_not_called()
    
    @given(
        org_id=st.text(min_size=1, max_size=20),
    )
    def test_delete_not_found_returns_error(self, org_id):
        """
        Property 11: Not Found Returns Error
        **Validates: Requirements 4.4**
        
        For any non-existent org_id, the use case should return ORGANIZATION_NOT_FOUND error.
        """
        # Setup
        repo = create_mock_repository(None)
        publisher = create_mock_event_publisher()
        use_case = DeleteOrganizationUseCase(repo, publisher)
        
        request = DeleteOrganizationRequest(org_id=org_id)
        
        # Execute
        response = use_case.execute(request)
        
        # Verify error
        assert response.success is False
        assert response.error_code == DeleteOrganizationError.ORGANIZATION_NOT_FOUND


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
