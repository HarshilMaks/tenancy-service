"""
Organization Lifecycle - State Machine for Organization Status Transitions

This module manages valid state transitions for Organizations (Tenants).
Modeled after Salesforce org lifecycle with modern SaaS additions.

State Flow:
                                    ┌──────────────────┐
                                    │   PROVISIONING   │
                                    └────────┬─────────┘
                                             │
                          ┌──────────────────┼──────────────────┐
                          ▼                  ▼                  ▼
                    ┌──────────┐      ┌──────────┐      ┌──────────────┐
                    │  TRIAL   │─────▶│  ACTIVE  │◀────▶│   MIGRATING  │
                    └────┬─────┘      └────┬─────┘      └──────────────┘
                         │                 │
                         │    ┌────────────┼────────────┐
                         │    ▼            ▼            ▼
                         │  ┌──────────┐ ┌─────────────────────┐
                         │  │SUSPENDED │ │PENDING_CANCELLATION │
                         │  └────┬─────┘ └──────────┬──────────┘
                         │       │                  │
                         └───────┴─────────┬────────┘
                                          ▼
                                   ┌──────────────┐
                                   │  TERMINATED  │
                                   └──────┬───────┘
                                          │ (within retention)
                                          ▼
                                   ┌──────────────┐
                                   │   RESTORED   │──▶ ACTIVE
                                   └──────────────┘
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from app.db.models.domain_models import (
    Organization,
    OrganizationStatus,
    SuspensionInfo,
    SuspensionReason,
    SuspensionSeverity,
    Region,
)


class InvalidStateTransition(Exception):
    """Raised when attempting an invalid org state transition."""
    
    def __init__(
        self,
        from_status: OrganizationStatus,
        to_status: OrganizationStatus,
        reason: str = ""
    ):
        self.from_status = from_status
        self.to_status = to_status
        self.reason = reason
        message = f"Cannot transition from {from_status.value} to {to_status.value}"
        if reason:
            message += f": {reason}"
        super().__init__(message)


class OrganizationNotRestorable(Exception):
    """Raised when trying to restore an org that cannot be restored."""
    pass


class OrganizationLifecycle:
    """
    Manages organization state transitions according to business rules.
    
    This is the single source of truth for what transitions are allowed.
    All state changes should go through this class.
    """
    
    # ========================================================================
    # VALID STATE TRANSITIONS
    # ========================================================================
    
    VALID_TRANSITIONS: Dict[OrganizationStatus, List[OrganizationStatus]] = {
        # From PROVISIONING: Can go to trial, active, or fail (terminate)
        OrganizationStatus.PROVISIONING: [
            OrganizationStatus.TRIAL,
            OrganizationStatus.ACTIVE,
            OrganizationStatus.TERMINATED,
        ],
        
        # From TRIAL: Can activate, suspend (trial expired), cancel, or terminate
        OrganizationStatus.TRIAL: [
            OrganizationStatus.ACTIVE,
            OrganizationStatus.SUSPENDED,
            OrganizationStatus.PENDING_CANCELLATION,
            OrganizationStatus.TERMINATED,
        ],
        
        # From ACTIVE: Can suspend, start cancellation, migrate, or terminate
        OrganizationStatus.ACTIVE: [
            OrganizationStatus.SUSPENDED,
            OrganizationStatus.PENDING_CANCELLATION,
            OrganizationStatus.MIGRATING,
            OrganizationStatus.TERMINATED,
        ],
        
        # From SUSPENDED: Can resume (active), cancel, or terminate
        OrganizationStatus.SUSPENDED: [
            OrganizationStatus.ACTIVE,
            OrganizationStatus.PENDING_CANCELLATION,
            OrganizationStatus.TERMINATED,
        ],
        
        # From PENDING_CANCELLATION: Can reactivate, suspend, or terminate
        OrganizationStatus.PENDING_CANCELLATION: [
            OrganizationStatus.ACTIVE,
            OrganizationStatus.SUSPENDED,
            OrganizationStatus.TERMINATED,
        ],
        
        # From MIGRATING: Can complete (active), fail (suspend), or abort (terminate)
        OrganizationStatus.MIGRATING: [
            OrganizationStatus.ACTIVE,
            OrganizationStatus.SUSPENDED,
            OrganizationStatus.TERMINATED,
        ],
        
        # From TERMINATED: Can restore to ACTIVE (within retention period)
        OrganizationStatus.TERMINATED: [
            OrganizationStatus.ACTIVE,  # Restore
        ],
    }
    
    # ========================================================================
    # TRANSITION VALIDATION
    # ========================================================================
    
    def can_transition(
        self,
        from_status: OrganizationStatus,
        to_status: OrganizationStatus
    ) -> bool:
        """
        Check if a state transition is valid.
        
        Args:
            from_status: Current org status
            to_status: Desired target status
            
        Returns:
            True if transition is allowed
        """
        # No-op transitions are considered invalid in our policy - tests expect explicit state changes.
        if from_status == to_status:
            return False
        
        valid_targets = self.VALID_TRANSITIONS.get(from_status, [])
        return to_status in valid_targets
    
    def validate_transition(
        self,
        from_status: OrganizationStatus,
        to_status: OrganizationStatus
    ) -> None:
        """
        Validate transition and raise exception if invalid.
        
        Args:
            from_status: Current org status
            to_status: Desired target status
            
        Raises:
            InvalidStateTransition: If transition is not allowed
        """
        if not self.can_transition(from_status, to_status):
            raise InvalidStateTransition(from_status, to_status)
    
    def get_valid_transitions(
        self,
        current_status: OrganizationStatus
    ) -> List[OrganizationStatus]:
        """Get list of valid target states from current status."""
        return self.VALID_TRANSITIONS.get(current_status, [])
    
    def is_terminal_state(self, status: OrganizationStatus) -> bool:
        """
        Check if a status is effectively terminal.
        
        Note: TERMINATED allows restoration within retention period,
        so it's not truly terminal.
        """
        return status == OrganizationStatus.TERMINATED
    
    # ========================================================================
    # STATE TRANSITION METHODS
    # ========================================================================
    
    def start_trial(
        self,
        org: Organization,
        trial_days: int = 14
    ) -> Organization:
        """
        Start trial period for a provisioning org.
        
        Args:
            org: The organization
            trial_days: Number of trial days (default 14)
            
        Returns:
            Updated organization
        """
        self.validate_transition(org.status, OrganizationStatus.TRIAL)
        org.start_trial(trial_days)
        return org
    
    def activate(self, org: Organization) -> Organization:
        """
        Activate an organization.
        
        Valid from: PROVISIONING, TRIAL, SUSPENDED, PENDING_CANCELLATION
        
        Args:
            org: The organization
            
        Returns:
            Updated organization
        """
        self.validate_transition(org.status, OrganizationStatus.ACTIVE)
        org.activate()
        return org
    
    def suspend(
        self,
        org: Organization,
        reason: SuspensionReason,
        severity: SuspensionSeverity,
        description: str,
        suspended_by: Optional[str] = None,
        auto_resume_at: Optional[datetime] = None,
        ticket_id: Optional[str] = None
    ) -> Organization:
        """
        Suspend an organization.
        
        Args:
            org: The organization
            reason: Predefined suspension reason
            severity: Suspension severity level
            description: Human-readable description
            suspended_by: User/system that initiated suspension
            auto_resume_at: When to auto-resume (for soft suspensions)
            ticket_id: Related support ticket
            
        Returns:
            Updated organization
        """
        self.validate_transition(org.status, OrganizationStatus.SUSPENDED)
        
        suspension_info = SuspensionInfo(
            reason=reason,
            severity=severity,
            description=description,
            suspended_at=datetime.now(timezone.utc),
            suspended_by=suspended_by or "SYSTEM",
            auto_resume_at=auto_resume_at,
            ticket_id=ticket_id,
        )
        
        org.suspend(suspension_info)
        return org
    
    def resume(self, org: Organization) -> Organization:
        """
        Resume a suspended organization.
        
        Args:
            org: The organization
            
        Returns:
            Updated organization
        """
        if org.status != OrganizationStatus.SUSPENDED:
            raise InvalidStateTransition(
                org.status,
                OrganizationStatus.ACTIVE,
                "Can only resume from SUSPENDED state"
            )
        
        org.resume()
        return org
    
    def start_cancellation(self, org: Organization) -> Organization:
        """
        Mark organization as pending cancellation.
        
        The org remains active until subscription_ends_at, then terminates.
        
        Args:
            org: The organization
            
        Returns:
            Updated organization
        """
        self.validate_transition(org.status, OrganizationStatus.PENDING_CANCELLATION)
        org.start_cancellation()
        return org
    
    def cancel_cancellation(self, org: Organization) -> Organization:
        """
        Cancel a pending cancellation (reactivate).
        
        Args:
            org: The organization in PENDING_CANCELLATION state
            
        Returns:
            Updated organization
        """
        if org.status != OrganizationStatus.PENDING_CANCELLATION:
            raise InvalidStateTransition(
                org.status,
                OrganizationStatus.ACTIVE,
                "Can only cancel cancellation from PENDING_CANCELLATION state"
            )
        
        org.activate()
        return org
    
    def start_migration(
        self,
        org: Organization,
        target_region: Region
    ) -> Organization:
        """
        Start region migration for an organization.
        
        Args:
            org: The organization
            target_region: Target region for migration
            
        Returns:
            Updated organization
        """
        self.validate_transition(org.status, OrganizationStatus.MIGRATING)
        
        # Store target region in metadata for migration process
        org.metadata["migration_target_region"] = target_region.value
        org.metadata["migration_started_at"] = datetime.now(timezone.utc).isoformat()
        
        org.start_migration()
        return org
    
    def complete_migration(
        self,
        org: Organization,
        new_region: Region
    ) -> Organization:
        """
        Complete region migration.
        
        Args:
            org: The organization in MIGRATING state
            new_region: The new region after migration
            
        Returns:
            Updated organization
        """
        if org.status != OrganizationStatus.MIGRATING:
            raise InvalidStateTransition(
                org.status,
                OrganizationStatus.ACTIVE,
                "Can only complete migration from MIGRATING state"
            )
        
        # Clear migration metadata
        org.metadata.pop("migration_target_region", None)
        org.metadata.pop("migration_started_at", None)
        
        org.complete_migration(new_region)
        return org
    
    def fail_migration(
        self,
        org: Organization,
        reason: str
    ) -> Organization:
        """
        Fail migration and suspend the org.
        
        Args:
            org: The organization in MIGRATING state
            reason: Reason for migration failure
            
        Returns:
            Updated organization (suspended)
        """
        if org.status != OrganizationStatus.MIGRATING:
            raise InvalidStateTransition(
                org.status,
                OrganizationStatus.SUSPENDED,
                "Can only fail migration from MIGRATING state"
            )
        
        # Clear migration metadata
        org.metadata.pop("migration_target_region", None)
        org.metadata["migration_failed_at"] = datetime.now(timezone.utc).isoformat()
        org.metadata["migration_failure_reason"] = reason
        
        return self.suspend(
            org,
            reason=SuspensionReason.ADMIN_ACTION,
            severity=SuspensionSeverity.HARD,
            description=f"Migration failed: {reason}",
            suspended_by="SYSTEM"
        )
    
    def terminate(
        self,
        org: Organization,
        reason: str,
        retention_days: int = 90
    ) -> Organization:
        """
        Terminate (soft delete) an organization.
        
        Data is retained for `retention_days` before permanent deletion.
        
        Args:
            org: The organization
            reason: Reason for termination
            retention_days: Days to retain data (default 90)
            
        Returns:
            Updated organization
        """
        self.validate_transition(org.status, OrganizationStatus.TERMINATED)
        org.terminate(reason, retention_days)
        return org
    
    def restore(self, org: Organization) -> Organization:
        """
        Restore a terminated organization.
        
        Only possible within the data retention period.
        
        Args:
            org: The terminated organization
            
        Returns:
            Restored organization (ACTIVE status)
            
        Raises:
            OrganizationNotRestorable: If org cannot be restored
        """
        if org.status != OrganizationStatus.TERMINATED:
            raise InvalidStateTransition(
                org.status,
                OrganizationStatus.ACTIVE,
                "Can only restore from TERMINATED state"
            )
        
        if not org.is_in_grace_period():
            raise OrganizationNotRestorable(
                f"Organization {org.org_id} is outside data retention period "
                f"(expired at {org.data_retention_until})"
            )
        
        org.restore()
        return org
    
    # ========================================================================
    # BULK OPERATIONS
    # ========================================================================
    
    def expire_trials(
        self,
        orgs: List[Organization]
    ) -> List[Organization]:
        """
        Process expired trials - suspend orgs with expired trials.
        
        Args:
            orgs: List of organizations to check
            
        Returns:
            List of organizations that were suspended
        """
        suspended = []
        
        for org in orgs:
            if org.status == OrganizationStatus.TRIAL and org.is_trial_expired():
                self.suspend(
                    org,
                    reason=SuspensionReason.TRIAL_EXPIRED,
                    severity=SuspensionSeverity.SOFT,
                    description="Trial period has expired. Please upgrade to continue.",
                    suspended_by="SYSTEM"
                )
                suspended.append(org)
        
        return suspended
    
    def complete_pending_cancellations(
        self,
        orgs: List[Organization]
    ) -> List[Organization]:
        """
        Process pending cancellations - terminate orgs past subscription end.
        
        Args:
            orgs: List of organizations to check
            
        Returns:
            List of organizations that were terminated
        """
        terminated = []
        
        for org in orgs:
            if org.status == OrganizationStatus.PENDING_CANCELLATION:
                if org.subscription_ends_at and datetime.now(timezone.utc) > org.subscription_ends_at:
                    self.terminate(org, "Subscription period ended after cancellation")
                    terminated.append(org)
        
        return terminated
    
    def purge_expired_terminations(
        self,
        orgs: List[Organization]
    ) -> List[Organization]:
        """
        Identify terminated orgs past retention period for permanent deletion.
        
        Note: This returns orgs to purge, doesn't actually delete them.
        Actual deletion should be handled by infrastructure layer.
        
        Args:
            orgs: List of terminated organizations
            
        Returns:
            List of organizations ready for permanent deletion
        """
        to_purge = []
        
        for org in orgs:
            if org.status == OrganizationStatus.TERMINATED:
                if not org.is_in_grace_period():
                    to_purge.append(org)
        
        return to_purge


# ============================================================================
# LIFECYCLE RULES - Helper functions
# ============================================================================

def get_suspension_severity_for_reason(reason: SuspensionReason) -> SuspensionSeverity:
    """
    Get default severity level for a suspension reason.
    
    Args:
        reason: The suspension reason
        
    Returns:
        Recommended severity level
    """
    severity_map = {
        # Soft - user can self-resolve
        SuspensionReason.PAYMENT_FAILED: SuspensionSeverity.SOFT,
        SuspensionReason.TRIAL_EXPIRED: SuspensionSeverity.SOFT,
        
        # Hard - requires support intervention
        SuspensionReason.PAYMENT_OVERDUE: SuspensionSeverity.HARD,
        SuspensionReason.TERMS_VIOLATION: SuspensionSeverity.HARD,
        SuspensionReason.ABUSE_DETECTED: SuspensionSeverity.HARD,
        SuspensionReason.ADMIN_ACTION: SuspensionSeverity.HARD,
        SuspensionReason.LEGAL_REQUEST: SuspensionSeverity.HARD,
        
        # Security - requires verification
        SuspensionReason.SECURITY_THREAT: SuspensionSeverity.SECURITY,
    }
    
    return severity_map.get(reason, SuspensionSeverity.HARD)


def get_description_for_suspension(
    reason: SuspensionReason,
    details: Optional[str] = None
) -> str:
    """
    Generate human-readable description for suspension reason.
    
    Args:
        reason: The suspension reason
        details: Optional additional details
        
    Returns:
        Human-readable description
    """
    descriptions = {
        SuspensionReason.PAYMENT_FAILED: 
            "Your payment method was declined. Please update your payment information to restore access.",
        SuspensionReason.PAYMENT_OVERDUE:
            "Your account has an overdue balance. Please contact billing to resolve.",
        SuspensionReason.TERMS_VIOLATION:
            "Your account has been suspended due to a violation of our Terms of Service.",
        SuspensionReason.SECURITY_THREAT:
            "Your account has been suspended due to suspicious activity. Please verify your identity.",
        SuspensionReason.ABUSE_DETECTED:
            "Your account has been suspended due to detected abuse of our platform.",
        SuspensionReason.LEGAL_REQUEST:
            "Your account has been suspended due to a legal request.",
        SuspensionReason.ADMIN_ACTION:
            "Your account has been suspended by an administrator.",
        SuspensionReason.TRIAL_EXPIRED:
            "Your trial period has ended. Please upgrade to a paid plan to continue using the platform.",
    }
    
    base_description = descriptions.get(reason, "Your account has been suspended.")
    
    if details:
        return f"{base_description} Details: {details}"
    
    return base_description


# ============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# ============================================================================

# Create a default lifecycle manager instance for convenience
_default_lifecycle = OrganizationLifecycle()


def can_transition(
    from_status: OrganizationStatus,
    to_status: OrganizationStatus
) -> bool:
    """
    Check if a state transition is valid.
    
    Convenience function that uses the default lifecycle manager.
    
    Args:
        from_status: Current org status
        to_status: Desired target status
        
    Returns:
        True if transition is allowed
    """
    return _default_lifecycle.can_transition(from_status, to_status)


def get_allowed_transitions(
    current_status: OrganizationStatus
) -> List[OrganizationStatus]:
    """
    Get list of valid target states from current status.
    
    Convenience function that uses the default lifecycle manager.
    
    Args:
        current_status: Current organization status
        
    Returns:
        List of allowed transition targets
    """
    return _default_lifecycle.get_valid_transitions(current_status)


def is_terminal_state(status: OrganizationStatus) -> bool:
    """
    Check if a status is effectively terminal.
    
    Convenience function that uses the default lifecycle manager.
    
    Args:
        status: Status to check
        
    Returns:
        True if status is terminal
    """
    return _default_lifecycle.is_terminal_state(status)
