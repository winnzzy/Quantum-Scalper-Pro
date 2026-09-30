# Private Launch Gate — December 2026

This build is intended for one owner and two markets: BTC/USDT and XAU/USD. A launch date is a planning target, not permission to trade. Real-money execution remains blocked until every gate below is evidenced.

## Non-negotiable gates

- [ ] Production uses a unique 32+ character `SECRET_KEY`, strong database/Redis/Grafana passwords, and the exact `OWNER_EMAIL`.
- [ ] The owner account is created once; a second `/auth/register` request returns `403`.
- [ ] Broker API credentials have trading permission only—no withdrawal permission—and IP allow-listing is enabled where supported.
- [ ] `EMERGENCY_STOP=true` is tested in staging and `/api/v1/system/emergency-stop` stops active loops.
- [ ] BTC/USDT and XAU/USD each have at least 30 elapsed paper-trading days and 100 closed paper trades.
- [ ] Both datasets pass the walk-forward, holdout, adverse-cost, drawdown, trade-count, and integrity qualification gates.
- [ ] Startup recovery is tested by restarting with an open testnet position and confirming broker/local reconciliation.
- [ ] Duplicate-signal, stale-quote, crossed-quote, excessive-spread, broker-timeout, and database-failure drills pass.
- [ ] A database backup is created, `gzip -t` passes, and a restore into a clean staging database is verified.
- [ ] Alerts reach the owner for engine stop, broker disconnect, daily-loss pause, recovery failure, and order rejection.

## Controlled rollout

1. **Now through October:** collect clean historical data, run qualification, and paper trade continuously.
2. **November:** freeze strategy parameters; run failure drills, backup restores, and a broker testnet soak without code changes.
3. **Early December:** if all gates are green, arm one market at minimum size and 0.25% risk per trade.
4. **After two stable weeks:** consider enabling the second market. Do not increase size during the observation period.

## Arming sequence

1. Keep `LIVE_TRADING_ENABLED=false` and call `GET /api/v1/system/launch-readiness`.
2. Resolve every returned blocker. Do not suppress or lower a threshold to meet the date.
3. Set `LIVE_TRADING_ENABLED=true`, redeploy, and call launch readiness again.
4. Verify broker balances and positions before starting a strategy.
5. Keep the emergency-stop endpoint and infrastructure access immediately available.

No strategy can guarantee profit or eliminate losses. The purpose of these gates is to prevent avoidable operational loss and require out-of-sample evidence before capital is exposed.
