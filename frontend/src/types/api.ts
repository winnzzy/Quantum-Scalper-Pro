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


export interface AuthUser {
  id: number;
  email: string;
  username: string;
  role: 'admin' | 'trader' | 'viewer' | 'affiliate';
  first_name?: string;
  last_name?: string;
  timezone?: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface StrategyConfigRequest {
  name: string;
  strategy_type: string;
  parameters: Record<string, number | string | boolean>;
  symbols: string[];
  timeframes: string[];
  risk_per_trade: number;
  is_active?: boolean;
}

export interface StrategyConfig extends StrategyConfigRequest {
  id: number;
  user_id: number;
  is_active: boolean;
}

export interface RiskProfile {
  risk_per_trade_percent: number;
  daily_loss_limit_percent: number;
  weekly_loss_limit_percent: number;
  max_drawdown_percent: number;
  max_consecutive_losses: number;
  max_open_trades: number;
  trading_paused: boolean;
  pause_reason?: string;
  mandatory_stop_loss?: boolean;
  spread_protection_enabled?: boolean;
  volatility_protection_enabled?: boolean;
  weekend_protection_enabled?: boolean;
  news_protection_enabled?: boolean;
}

export interface WalkForwardRequest {
  strategy_name: string;
  symbol: string;
  timeframe: '1m' | '5m' | '15m' | '30m' | '1h' | '4h' | '1d';
  initial_balance: number;
  parameter_candidates: Array<Record<string, number | string | boolean>>;
  train_candles: number;
  test_candles: number;
  step_candles?: number;
  min_train_trades: number;
}

export interface ValidationMetrics {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  gross_profit: number;
  gross_loss: number;
  net_pnl: number;
  profit_factor: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  error?: string;
}

export interface WalkForwardWindow {
  window: number;
  train_period: { start: string; end: string; candles: number };
  test_period: { start: string; end: string; candles: number };
  selected_parameters: Record<string, number | string | boolean>;
  training_metrics: ValidationMetrics;
  out_of_sample_metrics: ValidationMetrics;
}

export interface WalkForwardResult {
  strategy: string;
  symbol: string;
  timeframe: string;
  method: string;
  candidate_count: number;
  windows: WalkForwardWindow[];
  out_of_sample_summary: {
    window_count: number;
    positive_windows: number;
    positive_window_rate: number;
    total_trades: number;
    win_rate: number;
    gross_profit: number;
    gross_loss: number;
    net_pnl: number;
    profit_factor: number;
    worst_window_drawdown_pct: number;
    validation_status: 'promising' | 'not_robust' | 'insufficient_evidence';
  };
  interpretation: string;
  selection_bias_warning: string;
}
