import React from 'react';
import { useQuery, useMutation } from 'react-query';
import { riskAPI } from '../services/api';
import { toast } from 'react-hot-toast';
import { Shield, AlertTriangle, Pause, Play, Lock } from 'lucide-react';

const RiskCenter: React.FC = () => {
  const { data: profile, refetch } = useQuery('risk-profile', () => riskAPI.getProfile());
  const { data: events } = useQuery('risk-events', () => riskAPI.getEvents());

  const pauseMutation = useMutation(() => riskAPI.pauseTrading(), {
    onSuccess: () => {
      toast.success('Trading paused');
      refetch();
    },
  });

  const resumeMutation = useMutation(() => riskAPI.resumeTrading(), {
    onSuccess: () => {
      toast.success('Trading resumed');
      refetch();
    },
  });

  const p = profile?.data || {};
  const isPaused = p.trading_paused;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Risk Center</h1>
        {isPaused ? (
          <button
            onClick={() => resumeMutation.mutate()}
            className="flex items-center px-4 py-2 bg-success text-white rounded-lg hover:bg-green-600"
          >
            <Play className="w-4 h-4 mr-2" />
            Resume Trading
          </button>
        ) : (
          <button
            onClick={() => pauseMutation.mutate()}
            className="flex items-center px-4 py-2 bg-warning text-white rounded-lg hover:bg-yellow-600"
          >
            <Pause className="w-4 h-4 mr-2" />
            Pause Trading
          </button>
        )}
      </div>

      {/* Status Banner */}
      {isPaused && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-center">
          <AlertTriangle className="w-5 h-5 text-danger mr-3" />
          <div>
            <p className="font-medium text-danger">Trading Paused</p>
            <p className="text-sm text-red-600">{p.pause_reason}</p>
          </div>
        </div>
      )}

      {/* Risk Settings */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-lg font-semibold mb-4 flex items-center">
            <Shield className="w-5 h-5 mr-2 text-primary-600" />
            Risk Limits
          </h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
              <span className="text-sm">Risk Per Trade</span>
              <span className="font-semibold">{p.risk_per_trade_percent}%</span>
            </div>
            <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
              <span className="text-sm">Daily Loss Limit</span>
              <span className="font-semibold">{p.daily_loss_limit_percent}%</span>
            </div>
            <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
              <span className="text-sm">Weekly Loss Limit</span>
              <span className="font-semibold">{p.weekly_loss_limit_percent}%</span>
            </div>
            <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
              <span className="text-sm">Max Drawdown</span>
              <span className="font-semibold">{p.max_drawdown_percent}%</span>
            </div>
            <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
              <span className="text-sm">Max Consecutive Losses</span>
              <span className="font-semibold">{p.max_consecutive_losses}</span>
            </div>
            <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
              <span className="text-sm">Max Open Trades</span>
              <span className="font-semibold">{p.max_open_trades}</span>
            </div>
          </div>
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold mb-4 flex items-center">
            <Lock className="w-5 h-5 mr-2 text-primary-600" />
            Protections
          </h3>
          <div className="space-y-3">
            {[
              { label: 'Mandatory Stop Loss', enabled: p.mandatory_stop_loss },
              { label: 'Spread Protection', enabled: p.spread_protection_enabled },
              { label: 'Volatility Protection', enabled: p.volatility_protection_enabled },
              { label: 'Weekend Protection', enabled: p.weekend_protection_enabled },
              { label: 'News Protection', enabled: p.news_protection_enabled },
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <span className="text-sm">{item.label}</span>
                <span className={`px-2 py-1 rounded-full text-xs ${
                  item.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                }`}>
                  {item.enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Risk Events */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Recent Risk Events</h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Time</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Type</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Severity</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Message</th>
              </tr>
            </thead>
            <tbody>
              {(events?.data || []).slice(0, 10).map((event: any) => (
                <tr key={event.id} className="border-b border-gray-100">
                  <td className="py-3 px-4 text-sm">{new Date(event.created_at).toLocaleString()}</td>
                  <td className="py-3 px-4 text-sm capitalize">{event.event_type.replace('_', ' ')}</td>
                  <td className="py-3 px-4">
                    <span className={`px-2 py-1 rounded-full text-xs ${
                      event.severity === 'critical' ? 'bg-red-100 text-red-700' :
                      event.severity === 'warning' ? 'bg-yellow-100 text-yellow-700' :
                      'bg-blue-100 text-blue-700'
                    }`}>
                      {event.severity}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-sm">{event.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default RiskCenter;
