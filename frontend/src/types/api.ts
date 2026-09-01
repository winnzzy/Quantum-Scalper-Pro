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


export interface RealtimePosition {
  id: number;
  symbol: string;
  direction: 'buy' | 'sell';
  quantity: number | string;
  average_entry_price?: number | string;
  current_price?: number | string;
  unrealized_pnl?: number | string;
  stop_loss?: number | string;
  take_profit?: number | string;
}

export interface RealtimeTrade {
  id: number;
  symbol: string;
  direction: 'buy' | 'sell';
  quantity?: number | string;
  entry_price?: number | string;
  net_pnl?: number | string;
  stop_loss?: number | string;
  take_profit?: number | string;
}

export interface RealtimeNotification {
  id: number;
  type: string;
  title: string;
  message: string;
  priority: string;
  created_at: string;
}

export interface RealtimeSnapshot {
  type: 'snapshot';
  positions: RealtimePosition[];
  trades: RealtimeTrade[];
  notifications: RealtimeNotification[];
}
