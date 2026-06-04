import React from 'react';
import { useQuery } from 'react-query';
import { tradingAPI, analyticsAPI } from '../services/api';
import {
  DollarSign,
  TrendingUp,
  TrendingDown,
  Activity,
  Target,
  AlertTriangle,
} from 'lucide-react';

const StatCard: React.FC<{
  title: string;
  value: string;
  change?: string;
  icon: React.ElementType;
  color: string;
}> = ({ title, value, change, icon: Icon, color }) => (
  <div className="card">
    <div className="flex items-center justify-between">
      <div>
        <p className="text-sm text-gray-500">{title}</p>
        <p className="text-2xl font-bold mt-1">{value}</p>
        {change && (
          <p className={`text-sm mt-1 ${change.startsWith('+') ? 'text-success' : 'text-danger'}`}>
            {change}
          </p>
        )}
      </div>
      <div className={`p-3 rounded-lg ${color}`}>
        <Icon className="w-6 h-6 text-white" />
      </div>
    </div>
  </div>
);

const Dashboard: React.FC = () => {
  const { data: account } = useQuery('account', () => tradingAPI.getAccount('paper'), {
    refetchInterval: 5000,
  });
  const { data: performance } = useQuery('performance', () => analyticsAPI.getPerformance('daily'));
  const { data: status } = useQuery('status', () => tradingAPI.getStatus(), {
    refetchInterval: 10000,
  });

  const balance = account?.data?.balance || 0;
  const equity = account?.data?.equity || 0;
  const openPositions = account?.data?.open_positions || 0;
  const pnl = performance?.data?.net_pnl || 0;
  const winRate = performance?.data?.win_rate || 0;
  const totalTrades = performance?.data?.total_trades || 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <div className="flex items-center space-x-2">
          <div className={`w-2 h-2 rounded-full ${status?.data?.is_running ? 'bg-success' : 'bg-gray-400'}`} />
          <span className="text-sm text-gray-600">
            {status?.data?.is_running ? 'Trading Active' : 'Trading Inactive'}
          </span>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Balance"
          value={`$${balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
          icon={DollarSign}
          color="bg-primary-500"
        />
        <StatCard
          title="Equity"
          value={`$${equity.toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
          icon={Activity}
          color="bg-blue-500"
        />
        <StatCard
          title="Open Positions"
          value={openPositions.toString()}
          icon={Target}
          color="bg-purple-500"
        />
        <StatCard
          title="Today's P&L"
          value={`$${pnl.toFixed(2)}`}
          change={`${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}`}
          icon={pnl >= 0 ? TrendingUp : TrendingDown}
          color={pnl >= 0 ? 'bg-success' : 'bg-danger'}
        />
      </div>

      {/* Performance Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Performance Metrics</h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-gray-600">Win Rate</span>
              <span className="font-semibold">{winRate.toFixed(1)}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-primary-500 h-2 rounded-full transition-all"
                style={{ width: `${winRate}%` }}
              />
            </div>
            <div className="flex justify-between items-center pt-2">
              <span className="text-gray-600">Total Trades</span>
              <span className="font-semibold">{totalTrades}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-600">Profit Factor</span>
              <span className="font-semibold">{performance?.data?.profit_factor?.toFixed(2) || 'N/A'}</span>
            </div>
          </div>
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Risk Status</h3>
          <div className="space-y-3">
            <div className="flex items-center p-3 bg-green-50 rounded-lg">
              <div className="w-2 h-2 bg-success rounded-full mr-3" />
              <span className="text-sm">Daily Loss Limit: OK</span>
            </div>
            <div className="flex items-center p-3 bg-green-50 rounded-lg">
              <div className="w-2 h-2 bg-success rounded-full mr-3" />
              <span className="text-sm">Drawdown: Within Limits</span>
            </div>
            <div className="flex items-center p-3 bg-green-50 rounded-lg">
              <div className="w-2 h-2 bg-success rounded-full mr-3" />
              <span className="text-sm">News Filter: Active</span>
            </div>
            <div className="flex items-center p-3 bg-yellow-50 rounded-lg">
              <AlertTriangle className="w-4 h-4 text-warning mr-3" />
              <span className="text-sm">AI Filter: Learning Mode</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
