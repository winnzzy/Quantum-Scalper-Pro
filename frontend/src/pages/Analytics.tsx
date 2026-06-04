import React from 'react';
import { useQuery } from 'react-query';
import { analyticsAPI } from '../services/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { BarChart3, TrendingUp, Award, Target } from 'lucide-react';

const COLORS = ['#10b981', '#ef4444', '#0ea5e9', '#f59e0b', '#8b5cf6'];

const Analytics: React.FC = () => {
  const { data: daily } = useQuery('perf-daily', () => analyticsAPI.getPerformance('daily'));
  const { data: weekly } = useQuery('perf-weekly', () => analyticsAPI.getPerformance('weekly'));
  const { data: monthly } = useQuery('perf-monthly', () => analyticsAPI.getPerformance('monthly'));
  const { data: distribution } = useQuery('distribution', () => analyticsAPI.getDistribution());

  const perf = daily?.data || {};
  const weeklyPerf = weekly?.data || {};
  const monthlyPerf = monthly?.data || {};

  const winLossData = [
    { name: 'Wins', value: perf.winning_trades || 0 },
    { name: 'Losses', value: perf.losing_trades || 0 },
  ];

  const periodData = [
    { name: 'Daily', pnl: perf.net_pnl || 0 },
    { name: 'Weekly', pnl: weeklyPerf.net_pnl || 0 },
    { name: 'Monthly', pnl: monthlyPerf.net_pnl || 0 },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="card">
          <div className="flex items-center">
            <Target className="w-8 h-8 text-primary-500 mr-3" />
            <div>
              <p className="text-sm text-gray-500">Win Rate</p>
              <p className="text-2xl font-bold">{perf.win_rate?.toFixed(1)}%</p>
            </div>
          </div>
        </div>
        <div className="card">
          <div className="flex items-center">
            <TrendingUp className="w-8 h-8 text-success mr-3" />
            <div>
              <p className="text-sm text-gray-500">Net P&L</p>
              <p className="text-2xl font-bold">${perf.net_pnl?.toFixed(2)}</p>
            </div>
          </div>
        </div>
        <div className="card">
          <div className="flex items-center">
            <Award className="w-8 h-8 text-warning mr-3" />
            <div>
              <p className="text-sm text-gray-500">Profit Factor</p>
              <p className="text-2xl font-bold">{perf.profit_factor?.toFixed(2)}</p>
            </div>
          </div>
        </div>
        <div className="card">
          <div className="flex items-center">
            <BarChart3 className="w-8 h-8 text-purple-500 mr-3" />
            <div>
              <p className="text-sm text-gray-500">Total Trades</p>
              <p className="text-2xl font-bold">{perf.total_trades}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-lg font-semibold mb-4">P&L by Period</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={periodData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip formatter={(value: number) => `$${value.toFixed(2)}`} />
              <Bar dataKey="pnl" fill="#0ea5e9" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Win/Loss Distribution</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={winLossData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={5}
                dataKey="value"
              >
                {winLossData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex justify-center space-x-4 mt-2">
            {winLossData.map((entry, index) => (
              <div key={entry.name} className="flex items-center">
                <div className="w-3 h-3 rounded-full mr-2" style={{ backgroundColor: COLORS[index] }} />
                <span className="text-sm">{entry.name}: {entry.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Distribution Table */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Performance by Symbol</h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Symbol</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Strategy</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Trades</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">P&L</th>
              </tr>
            </thead>
            <tbody>
              {(distribution?.data || []).map((item: any, index: number) => (
                <tr key={index} className="border-b border-gray-100">
                  <td className="py-3 px-4 font-medium">{item.symbol}</td>
                  <td className="py-3 px-4">{item.strategy}</td>
                  <td className="py-3 px-4">{item.trades}</td>
                  <td className={`py-3 px-4 font-medium ${item.pnl >= 0 ? 'text-success' : 'text-danger'}`}>
                    ${item.pnl.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Analytics;
