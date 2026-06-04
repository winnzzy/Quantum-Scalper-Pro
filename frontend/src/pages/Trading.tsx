import React, { useState } from 'react';
import { useQuery, useMutation } from 'react-query';
import { tradingAPI, strategyAPI } from '../services/api';
import { toast } from 'react-hot-toast';
import { Play, Square, RefreshCw, TrendingUp, TrendingDown } from 'lucide-react';

const Trading: React.FC = () => {
  const [selectedSymbol, setSelectedSymbol] = useState('BTC/USDT');
  const [selectedStrategy, setSelectedStrategy] = useState('ema_scalper');
  const [selectedBroker, setSelectedBroker] = useState('paper');

  const { data: marketData, refetch: refetchMarket } = useQuery(
    ['market', selectedSymbol],
    () => tradingAPI.getMarketData(selectedSymbol),
    { refetchInterval: 5000 }
  );

  const { data: strategies } = useQuery('strategies', () => strategyAPI.list());
  const { data: status, refetch: refetchStatus } = useQuery('tradingStatus', () => tradingAPI.getStatus());

  const startMutation = useMutation(
    (configId: number) => tradingAPI.startTrading(configId),
    {
      onSuccess: () => {
        toast.success('Trading started!');
        refetchStatus();
      },
      onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to start'),
    }
  );

  const stopMutation = useMutation(
    () => tradingAPI.stopTrading(),
    {
      onSuccess: () => {
        toast.success('Trading stopped!');
        refetchStatus();
      },
      onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to stop'),
    }
  );

  const market = marketData?.data;
  const isRunning = status?.data?.is_running;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Trading Control</h1>
        <div className="flex items-center space-x-4">
          <button
            onClick={() => refetchMarket()}
            className="p-2 text-gray-600 hover:text-primary-600 transition-colors"
          >
            <RefreshCw className="w-5 h-5" />
          </button>
          {isRunning ? (
            <button
              onClick={() => stopMutation.mutate()}
              disabled={stopMutation.isLoading}
              className="flex items-center px-4 py-2 bg-danger text-white rounded-lg hover:bg-red-600 transition-colors"
            >
              <Square className="w-4 h-4 mr-2" />
              {stopMutation.isLoading ? 'Stopping...' : 'Stop Trading'}
            </button>
          ) : (
            <button
              onClick={() => startMutation.mutate(1)}
              disabled={startMutation.isLoading}
              className="flex items-center px-4 py-2 bg-success text-white rounded-lg hover:bg-green-600 transition-colors"
            >
              <Play className="w-4 h-4 mr-2" />
              {startMutation.isLoading ? 'Starting...' : 'Start Trading'}
            </button>
          )}
        </div>
      </div>

      {/* Market Data */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="card lg:col-span-2">
          <h3 className="text-lg font-semibold mb-4">Market Data - {selectedSymbol}</h3>
          {market && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-500">Bid</p>
                <p className="text-xl font-bold">{market.bid?.toFixed(2)}</p>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-500">Ask</p>
                <p className="text-xl font-bold">{market.ask?.toFixed(2)}</p>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-500">Spread</p>
                <p className="text-xl font-bold">{market.spread?.toFixed(4)}</p>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-500">24h Volume</p>
                <p className="text-xl font-bold">{(market.volume_24h / 1e6)?.toFixed(2)}M</p>
              </div>
            </div>
          )}
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Configuration</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Symbol</label>
              <select
                value={selectedSymbol}
                onChange={(e) => setSelectedSymbol(e.target.value)}
                className="input"
              >
                <option>BTC/USDT</option>
                <option>ETH/USDT</option>
                <option>EUR/USD</option>
                <option>GBP/USD</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Strategy</label>
              <select
                value={selectedStrategy}
                onChange={(e) => setSelectedStrategy(e.target.value)}
                className="input"
              >
                {strategies?.data?.strategies?.map((s: string) => (
                  <option key={s} value={s}>{s.replace('_', ' ').toUpperCase()}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Broker</label>
              <select
                value={selectedBroker}
                onChange={(e) => setSelectedBroker(e.target.value)}
                className="input"
              >
                <option value="paper">Paper Trading</option>
                <option value="binance_testnet">Binance Testnet</option>
                <option value="binance_futures">Binance Futures</option>
                <option value="mt5">MetaTrader 5</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Trading Status */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Engine Status</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="p-4 bg-gray-50 rounded-lg">
            <p className="text-sm text-gray-500">Status</p>
            <div className="flex items-center mt-1">
              <div className={`w-2 h-2 rounded-full mr-2 ${isRunning ? 'bg-success' : 'bg-gray-400'}`} />
              <span className="font-semibold">{isRunning ? 'Running' : 'Stopped'}</span>
            </div>
          </div>
          <div className="p-4 bg-gray-50 rounded-lg">
            <p className="text-sm text-gray-500">Active Tasks</p>
            <p className="text-xl font-bold">{status?.data?.active_tasks || 0}</p>
          </div>
          <div className="p-4 bg-gray-50 rounded-lg">
            <p className="text-sm text-gray-500">Open Trades</p>
            <p className="text-xl font-bold">{status?.data?.open_trades || 0}</p>
          </div>
          <div className="p-4 bg-gray-50 rounded-lg">
            <p className="text-sm text-gray-500">Broker</p>
            <p className="text-lg font-bold capitalize">{selectedBroker.replace('_', ' ')}</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Trading;
