import React, { FormEvent, useState } from 'react';
import { useMutation, useQuery } from 'react-query';
import { AlertTriangle, CheckCircle2, FlaskConical, XCircle } from 'lucide-react';
import { toast } from 'react-hot-toast';

import { backtestingAPI, strategyAPI } from '../services/api';
import { WalkForwardRequest, WalkForwardResult } from '../types/api';
import { getApiErrorMessage } from '../utils/errors';


const statusStyle = {
  promising: {
    label: 'Promising',
    className: 'bg-green-100 text-green-800',
    icon: CheckCircle2,
  },
  not_robust: {
    label: 'Not robust',
    className: 'bg-red-100 text-red-800',
    icon: XCircle,
  },
  insufficient_evidence: {
    label: 'Insufficient evidence',
    className: 'bg-yellow-100 text-yellow-800',
    icon: AlertTriangle,
  },
};

const formatNumber = (value: number, digits = 2) =>
  Number.isFinite(value) ? value.toFixed(digits) : '∞';

const Validation: React.FC = () => {
  const { data: strategies } = useQuery('strategy-list', () => strategyAPI.list());
  const strategyList: string[] = strategies?.data?.strategies || [];
  const [result, setResult] = useState<WalkForwardResult | null>(null);
  const [candidateText, setCandidateText] = useState('[\n  {}\n]');
  const [form, setForm] = useState<Omit<WalkForwardRequest, 'parameter_candidates'>>({
    strategy_name: 'ema_scalper',
    symbol: 'BTC/USDT',
    timeframe: '1m',
    initial_balance: 100000,
    train_candles: 1000,
    test_candles: 250,
    step_candles: 250,
    min_train_trades: 5,
  });

  const mutation = useMutation(
    (request: WalkForwardRequest) => backtestingAPI.runWalkForward(request),
    {
      onSuccess: (response) => {
        setResult(response.data);
        toast.success('Walk-forward validation completed');
      },
      onError: (error: unknown) => {
        toast.error(getApiErrorMessage(error, 'Validation failed'));
      },
    }
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    let candidates: WalkForwardRequest['parameter_candidates'];
    try {
      const parsed = JSON.parse(candidateText);
      if (!Array.isArray(parsed) || parsed.length < 1 || parsed.length > 20) {
        throw new Error('Use a JSON array containing 1 to 20 parameter objects.');
      }
      if (parsed.some((candidate) => !candidate || Array.isArray(candidate) || typeof candidate !== 'object')) {
        throw new Error('Every candidate must be a JSON object.');
      }
      candidates = parsed;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Invalid candidate JSON');
      return;
    }

    setResult(null);
    mutation.mutate({ ...form, parameter_candidates: candidates });
  };

  const summary = result?.out_of_sample_summary;
  const status = summary ? statusStyle[summary.validation_status] : null;
  const StatusIcon = status?.icon;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center text-2xl font-bold text-gray-900">
          <FlaskConical className="mr-3 h-6 w-6 text-primary-600" />
          Walk-Forward Validation
        </h1>
        <p className="mt-2 text-sm text-gray-600">
          Select parameters on past data, then measure them on the next unseen period.
          Historical CSV data must already exist on the server for this symbol and timeframe.
        </p>
      </div>

      <form onSubmit={submit} className="card space-y-5">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <label className="text-sm font-medium text-gray-700">
            Strategy
            <select
              className="input mt-1"
              value={form.strategy_name}
              onChange={(event) => setForm({ ...form, strategy_name: event.target.value })}
            >
              {(strategyList.length ? strategyList : ['ema_scalper']).map((name) => (
                <option key={name} value={name}>{name.replaceAll('_', ' ')}</option>
              ))}
            </select>
          </label>
          <label className="text-sm font-medium text-gray-700">
            Symbol
            <input
              className="input mt-1"
              value={form.symbol}
              onChange={(event) => setForm({ ...form, symbol: event.target.value.toUpperCase() })}
              required
            />
          </label>
          <label className="text-sm font-medium text-gray-700">
            Timeframe
            <select
              className="input mt-1"
              value={form.timeframe}
              onChange={(event) => setForm({ ...form, timeframe: event.target.value as WalkForwardRequest['timeframe'] })}
            >
              {['1m', '5m', '15m', '30m', '1h', '4h', '1d'].map((timeframe) => (
                <option key={timeframe}>{timeframe}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          {[
            ['Initial balance', 'initial_balance', 1],
            ['Training candles', 'train_candles', 60],
            ['Test candles', 'test_candles', 60],
            ['Step candles', 'step_candles', 1],
            ['Min. train trades', 'min_train_trades', 1],
          ].map(([label, key, minimum]) => (
            <label key={String(key)} className="text-sm font-medium text-gray-700">
              {label}
              <input
                type="number"
                className="input mt-1"
                min={Number(minimum)}
                value={form[key as keyof typeof form] as number}
                onChange={(event) => setForm({ ...form, [key]: Number(event.target.value) })}
                required
              />
            </label>
          ))}
        </div>

        <label className="block text-sm font-medium text-gray-700">
          Parameter candidates (JSON array, maximum 20)
          <textarea
            className="input mt-1 min-h-[130px] font-mono text-sm"
            value={candidateText}
            onChange={(event) => setCandidateText(event.target.value)}
            spellCheck={false}
          />
          <span className="mt-1 block text-xs font-normal text-gray-500">
            Example: {`[{"min_adx": 18}, {"min_adx": 22}]`}. More candidates increase overfitting risk.
          </span>
        </label>

        <button type="submit" className="btn-primary" disabled={mutation.isLoading}>
          {mutation.isLoading ? 'Running validation…' : 'Run validation'}
        </button>
      </form>

      {summary && status && StatusIcon && (
        <>
          <div className="card flex flex-col justify-between gap-4 md:flex-row md:items-center">
            <div>
              <p className="text-sm text-gray-500">Out-of-sample assessment</p>
              <div className={`mt-2 inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold ${status.className}`}>
                <StatusIcon className="mr-2 h-4 w-4" />
                {status.label}
              </div>
            </div>
            <p className="max-w-2xl text-sm text-gray-600">{result?.interpretation}</p>
          </div>

          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            {[
              ['Net P&L', formatNumber(summary.net_pnl)],
              ['Profit factor', formatNumber(summary.profit_factor)],
              ['Win rate', `${formatNumber(summary.win_rate)}%`],
              ['Positive windows', `${formatNumber(summary.positive_window_rate)}%`],
              ['Worst drawdown', `${formatNumber(summary.worst_window_drawdown_pct)}%`],
            ].map(([label, value]) => (
              <div key={label} className="card p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
                <p className="mt-2 text-xl font-bold text-gray-900">{value}</p>
              </div>
            ))}
          </div>

          <div className="card">
            <h2 className="text-lg font-semibold text-gray-900">Chronological windows</h2>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[900px]">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
                    <th className="px-3 py-3">Window</th>
                    <th className="px-3 py-3">Unseen period</th>
                    <th className="px-3 py-3">Parameters selected</th>
                    <th className="px-3 py-3">Trades</th>
                    <th className="px-3 py-3">Win rate</th>
                    <th className="px-3 py-3">Profit factor</th>
                    <th className="px-3 py-3">Net P&L</th>
                    <th className="px-3 py-3">Drawdown</th>
                  </tr>
                </thead>
                <tbody>
                  {result?.windows.map((window) => {
                    const metrics = window.out_of_sample_metrics;
                    return (
                      <tr key={window.window} className="border-b border-gray-100 text-sm">
                        <td className="px-3 py-3 font-medium">{window.window}</td>
                        <td className="px-3 py-3 text-gray-600">
                          {new Date(window.test_period.start).toLocaleDateString()} –{' '}
                          {new Date(window.test_period.end).toLocaleDateString()}
                        </td>
                        <td className="max-w-xs truncate px-3 py-3 font-mono text-xs" title={JSON.stringify(window.selected_parameters)}>
                          {JSON.stringify(window.selected_parameters)}
                        </td>
                        <td className="px-3 py-3">{metrics.total_trades ?? '—'}</td>
                        <td className="px-3 py-3">{metrics.error ? 'Error' : `${formatNumber(metrics.win_rate)}%`}</td>
                        <td className="px-3 py-3">{metrics.error ? '—' : formatNumber(metrics.profit_factor)}</td>
                        <td className={`px-3 py-3 font-medium ${metrics.net_pnl >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                          {metrics.error ? '—' : formatNumber(metrics.net_pnl)}
                        </td>
                        <td className="px-3 py-3">{metrics.error ? '—' : `${formatNumber(metrics.max_drawdown_pct)}%`}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-800">
            <strong>Holdout warning:</strong> {result?.selection_bias_warning}
          </div>
        </>
      )}
    </div>
  );
};

export default Validation;
