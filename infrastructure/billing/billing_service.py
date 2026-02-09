class BillingService:
    """Integrates with external billing provider"""
    
    def create_account(self, tenant_id: UUID, plan: PlanTier) -> BillingAccount:
        """Create billing account in Stripe"""
        response = stripe.Customer.create(
            metadata={"tenant_id": str(tenant_id)},
            description=f"Tenant {tenant_id}"
        )
        
        # Subscribe to plan
        stripe.Subscription.create(
            customer=response.id,
            items=[{"price": self.plan_to_price_id(plan)}]
        )
        
        return BillingAccount(
            id=response.id,
            tenant_id=tenant_id
        )