export interface SubscriptionPlan {
  id: number;
  tier: string;
  billing_interval: 'monthly' | 'annual' | 'lifetime';
  price: number;
  currency: string;
  display_name: string;
  description?: string;
  features: string[];
  trial_days: number;
  max_devices: number;
  max_strategies: number;
  max_broker_accounts: number;
}

export interface CustomerSubscription {
  id: number;
  status: string;
  plan_tier: string;
  billing_interval: string;
  current_period_end?: string;
  cancel_at_period_end: boolean;
  trial_end?: string;
  is_trial: boolean;
  price: number;
  currency: string;
  features: string[];
}

export interface CheckoutResponse {
  checkout_url: string;
  checkout_session_id: string;
  expires_at: number;
}

export interface PortalResponse {
  portal_url: string;
}
