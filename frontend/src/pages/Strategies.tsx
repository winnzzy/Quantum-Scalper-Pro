import React, { useState } from 'react';
import { useQuery, useMutation } from 'react-query';
import { strategyAPI } from '../services/api';
import { toast } from 'react-hot-toast';
import { Zap, Settings, Plus, Check } from 'lucide-react';

const Strategies: React.FC = () => {
  const { data: strategies } = useQuery('strategy-list', () => strategyAPI.list());
  const { data: configs } = useQuery('strategy-configs', () => strategyAPI.getConfigs());
  const [selectedStrategy, setSelectedStrategy] = useState('');
  const [showConfig, setShowConfig] = useState(false);
  const [configForm, setConfigForm] = useState({
    name: '',
    symbols: ['BTC/USDT'],
    timeframes: ['1m'],
    risk_per_trade: 0.5,
    parameters: {},
  });

  const createMutation = useMutation(
    (data: any) => strategyAPI.createConfig(data),
    {
      onSuccess: () => {
        toast.success('Strategy configured!');
        setShowConfig(false);
      },
      onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed'),
    }
  );

  const strategyList = strategies?.data?.strategies || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Strategies</h1>
        <button
          onClick={() => setShowConfig(true)}
          className="flex items-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
        >
          <Plus className="w-4 h-4 mr-2" />
          New Configuration
        </button>
      </div>

      {/* Strategy Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {strategyList.map((name: string) => (
          <div key={name} className="card hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between">
              <div className="flex items-center">
                <div className="p-3 bg-primary-100 rounded-lg">
                  <Zap className="w-6 h-6 text-primary-600" />
                </div>
                <div className="ml-4">
                  <h3 className="font-semibold text-lg capitalize">{name.replace('_', ' ')}</h3>
                  <p className="text-sm text-gray-500">Scalping Strategy</p>
                </div>
              </div>
              <button
                onClick={() => setSelectedStrategy(name)}
                className="p-2 text-gray-400 hover:text-primary-600"
              >
                <Settings className="w-5 h-5" />
              </button>
            </div>
            <div className="mt-4 flex items-center space-x-2">
              <span className="px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full">Active</span>
              <span className="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded-full">Scalping</span>
            </div>
          </div>
        ))}
      </div>

      {/* Active Configs */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Active Configurations</h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Name</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Type</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Symbols</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Status</th>
              </tr>
            </thead>
            <tbody>
              {(configs?.data || []).map((config: any) => (
                <tr key={config.id} className="border-b border-gray-100">
                  <td className="py-3 px-4 font-medium">{config.name}</td>
                  <td className="py-3 px-4 capitalize">{config.strategy_type.replace('_', ' ')}</td>
                  <td className="py-3 px-4">{config.symbols?.join(', ')}</td>
                  <td className="py-3 px-4">
                    <span className={`px-2 py-1 rounded-full text-xs ${
                      config.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                    }`}>
                      {config.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Config Modal */}
      {showConfig && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-full max-w-lg">
            <h3 className="text-lg font-semibold mb-4">Configure Strategy</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                <input
                  type="text"
                  value={configForm.name}
                  onChange={(e) => setConfigForm({ ...configForm, name: e.target.value })}
                  className="input"
                  placeholder="My Strategy"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Strategy Type</label>
                <select className="input">
                  {strategyList.map((s: string) => (
                    <option key={s} value={s}>{s.replace('_', ' ')}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Risk Per Trade (%)</label>
                <input
                  type="number"
                  value={configForm.risk_per_trade}
                  onChange={(e) => setConfigForm({ ...configForm, risk_per_trade: parseFloat(e.target.value) })}
                  className="input"
                  step="0.1"
                  min="0.1"
                  max="5"
                />
              </div>
            </div>
            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => setShowConfig(false)}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={() => createMutation.mutate(configForm)}
                className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
              >
                Save Configuration
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Strategies;
