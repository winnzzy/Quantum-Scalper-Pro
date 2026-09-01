import axios from 'axios';
import { useAuthStore } from '../store/authStore';
import {
  CheckoutResponse,
  CustomerSubscription,
  PortalResponse,
  SubscriptionPlan,
  AuthTokens,
  AuthUser,
  RegisterRequest,
  StrategyConfig,
  StrategyConfigRequest,
  RiskProfile,
} from '../types/api';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export const authAPI = {
  login: (email: string, password: string) =>
    api.post<AuthTokens>('/auth/login', { username: email, password }),
  register: (data: RegisterRequest) => api.post<AuthUser>('/auth/register', data),
  me: () => api.get<AuthUser>('/auth/me'),
};

export const tradingAPI = {
  getTrades: (status?: string) => api.get('/trading/trades', { params: { status } }),
  getPositions: () => api.get('/trading/positions'),
  getAccount: (broker?: string) => api.get('/trading/account', { params: { broker_type: broker } }),
  getMarketData: (symbol: string) => api.get(`/trading/market/${symbol}`),
  closeTrade: (id: number) => api.post(`/trading/trades/${id}/close`),
  startTrading: (configId: number) => api.post('/trading/start', { strategy_config_id: configId }),
  stopTrading: () => api.post('/trading/stop'),
  getStatus: () => api.get('/trading/status'),
};

export const strategyAPI = {
  list: () => api.get('/strategies/list'),
  getInfo: (name: string) => api.get(`/strategies/${name}/info`),
  getConfigs: () => api.get<StrategyConfig[]>('/trading/strategies/configs'),
  createConfig: (data: StrategyConfigRequest) =>
    api.post<StrategyConfig>('/trading/strategies/configs', data),
};

export const riskAPI = {
  getProfile: () => api.get<RiskProfile>('/risk/profile'),
  updateProfile: (data: Partial<RiskProfile>) => api.put<RiskProfile>('/risk/profile', data),
  pauseTrading: () => api.post('/risk/pause'),
  resumeTrading: () => api.post('/risk/resume'),
  getEvents: () => api.get('/risk/events'),
};

export const analyticsAPI = {
  getPerformance: (period: string) => api.get('/analytics/performance', { params: { period } }),
  getDistribution: () => api.get('/analytics/trades/distribution'),
};


export const billingAPI = {
  getPlans: () => api.get<{ plans: SubscriptionPlan[] }>('/billing/plans'),
  getSubscription: () =>
    api.get<{ subscription: CustomerSubscription | null }>('/billing/subscription'),
  createCheckout: (planId: number) =>
    api.post<CheckoutResponse>('/billing/checkout', { plan_id: planId }),
  createPortal: () => api.post<PortalResponse>('/billing/portal', {}),
  cancel: (atPeriodEnd = true, reason?: string) =>
    api.post('/billing/cancel', { at_period_end: atPeriodEnd, reason }),
};
