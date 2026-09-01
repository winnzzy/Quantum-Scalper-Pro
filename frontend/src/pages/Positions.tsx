import React from 'react';
import { useQuery, useMutation } from 'react-query';
import { tradingAPI } from '../services/api';
import { toast } from 'react-hot-toast';
import { X, TrendingUp, TrendingDown, Clock } from 'lucide-react';

const Positions: React.FC = () => {
  const { data: positions, refetch } = useQuery('positions', () => tradingAPI.getPositions());
  const { data: trades } = useQuery('trades', () => tradingAPI.getTrades('open'));

  const closeMutation = useMutation(
    (tradeId: number) => tradingAPI.closeTrade(tradeId),
    {
      onSuccess: () => {
        toast.success('Position closed!');
        refetch();
      },
      onError: (error: any) => toast.error(error.response?.data?.detail || 'Close failed'),
    }
  );

  const allPositions = [...(positions?.data || []), ...(trades?.data || [])];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Positions & Orders</h1>

      <div className="card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Symbol</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Direction</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Quantity</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Entry Price</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Current Price</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">P&L</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">SL / TP</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Actions</th>
              </tr>
            </thead>
            <tbody>
              {allPositions.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-gray-500">
                    No open positions
                  </td>
                </tr>
              ) : (
                allPositions.map((position: any) => (
                  <tr key={position.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-3 px-4 font-medium">{position.symbol}</td>
                    <td className="py-3 px-4">
                      <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                        position.direction === 'buy' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                      }`}>
                        {position.direction === 'buy' ? <TrendingUp className="w-3 h-3 mr-1" /> : <TrendingDown className="w-3 h-3 mr-1" />}
                        {position.direction?.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-3 px-4">{position.quantity}</td>
                    <td className="py-3 px-4">{position.entry_price || position.average_entry_price}</td>
                    <td className="py-3 px-4">{position.current_price || '-'}</td>
                    <td className={`py-3 px-4 font-medium ${
                      (position.unrealized_pnl || position.net_pnl || 0) >= 0 ? 'text-success' : 'text-danger'
                    }`}>
                      {(position.unrealized_pnl || position.net_pnl || 0).toFixed(2)}
                    </td>
                    <td className="py-3 px-4 text-sm">
                      <div>SL: {position.stop_loss || '-'}</div>
                      <div>TP: {position.take_profit || '-'}</div>
                    </td>
                    <td className="py-3 px-4">
                      <button
                        onClick={() => closeMutation.mutate(position.id)}
                        disabled={closeMutation.isLoading}
                        className="p-2 text-danger hover:bg-red-50 rounded-lg transition-colors"
                        title="Close Position"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Positions;
