# Important Findings

Date: 2026-08-14

These findings capture the current state of the Indian intraday paper-trading system after ECS, Oracle/Breeze, DynamoDB, and micro-trading log reviews. They should be treated as live-readiness blockers or tuning evidence, not casual notes.

## Fix Status

Implemented on 2026-08-14, pending ECS redeploy and live paper-log verification:

- Market-open startup sleep no longer uses a fixed one-hour sleep; it polls up to `market_closed_poll_seconds`, currently 60 seconds.
- Micro position exits now have a separate monitor loop controlled by `micro_exit_check_interval_seconds`, currently 30 seconds.
- Startup position reconciliation now closes stale paper-position snapshots and blocks live entries if open positions exist but live broker reconciliation cannot be proven.
- Normal market-service startup now skips overnight analysis by default with `run_startup_overnight_analysis=false`, because the ICICI Breeze session key must be refreshed manually each day before ECS is started.
- Micro entry scans now use fixed-rate scheduling from cycle start. A 90-second scan interval with a 25-second scan sleeps about 65 seconds instead of 90 seconds.
- Cost-aware entry gating is calibrated to the user's ICICI Direct PRIME 4999 intraday plan: 1 bps brokerage, 2 bps statutory/tax buffer, and 2 bps slippage buffer, for 5 bps total on round-trip turnover.

## High Priority Findings

1. The system is not ready for real-money trading yet.
   Paper trading is running and the micro engine can generate entries/exits, but real trading should wait until P12 high-priority items are fixed and proven for at least one clean paper day.

2. Market-open startup previously could miss the open.
   A bot started before 09:15 IST could enter the outside-market branch and sleep for 3600 seconds. This is now fixed in code with a configurable short poll, but must be verified in ECS logs after deploy.

3. Exit monitoring was coupled to the entry scan loop.
   The system previously evaluated exits as part of the same market cycle that scans symbols. A separate 30-second exit monitor has now been added in code, but it must be verified in ECS logs and paper-trade exits after deploy.

4. Position reconciliation remains a live-readiness gate.
   During paper review, DynamoDB still showed stale/open position state from a prior session, including stale RELIANCE exposure. Startup stale-paper cleanup and live-entry blocking have been implemented, but real live mode still needs broker/Breeze position listing before live trading is allowed.

5. Manual daily startup is the correct operating assumption for now.
   Because the ICICI Breeze session key resets daily after 12 and must be refreshed manually, the ECS service should be started manually after the key is updated. The bot must tolerate starting early, exactly at open, or late; the current code now polls shortly before open, starts immediately if already inside market hours, and does not run overnight analysis on normal service startup.

5. Oracle/Breeze reliability is still a profit and safety risk.
   The system has seen quote/OHLCV connection refusals, 503s, timeouts, and empty OHLCV responses. The bot must continue to fail closed on stale or unavailable data, but it also needs better retry/backoff, telemetry, and alarms so temporary collector issues do not silently suppress all trading or delay exits.

## Trading Logic Findings

0. Small target moves can lose after realistic costs.
   Paper logs on 2026-08-14 showed trades such as JSWSTEEL where gross price movement was positive but net P&L became negative after brokerage/taxes/slippage. P13-WP07 adds a cost-aware entry gate so the bot skips entries whose expected target profit cannot clear estimated round-trip costs with a buffer.

0a. Fixed INR profit floors do not scale with paper/live notional.
   The 2026-08-17 paper run with INR 10 crore capital showed that a fixed INR 1000 expected-net threshold is meaningless for large positions. P13-WP07 now adds `micro_min_expected_net_profit_bps`; production uses 8 bps so the minimum expected net profit scales with entry notional.

0b. First-candle continuation entries were too reactive.
   Paper logs showed many high-volume entries fading within 2-3 minutes and exiting via `early_invalidation:volume_collapse`. P13-WP03 now requires second-candle continuation confirmation for ordinary volume-continuation entries, while preserving an exceptional first-candle path for at least 8x relative volume with controlled VWAP extension.

0c. ECS restart must not reset risk memory.
   Paper logs on 2026-08-18 showed DynamoDB/dashboard correctly reporting today's losses while the restarted bot heartbeat had `daily_pnl=0.0`. P13-WP08 now restores today's closed micro exits from DynamoDB on startup, rebuilding `daily_pnl`, consecutive-loss count, setup expectancy, and recent per-symbol loss throttle state before the first heartbeat.

1. The current micro entry filters are not obviously wrong.
   The checks for fresh 1-minute candles, relative volume, ATR volatility, VWAP extension, RSI/MACD/trend alignment, confidence, and risk approval are a sensible first paper-trading framework.

2. The 10-minute max hold is not the main flaw.
   Ten minutes is acceptable for the current micro strategy, provided exits are checked independently and quickly. The bigger issue is exit-check latency, not the 10-minute value itself.

3. The 5-minute same-stock cooldown is reasonable for now.
   `micro_reentry_cooldown_seconds=300` should reduce duplicate churn while still allowing second-wave entries. It should be reviewed against paper evidence, not guessed.

4. Configured scan interval is now fixed-rate from cycle start.
   The previous runtime behaved like `scan duration + sleep`. It now subtracts scan duration from the configured interval and logs cycle duration, next sleep, or overrun.

5. Continuation volatility logging can be confusing.
   The detector can log normal volatility failure while still allowing a continuation setup under the lower continuation ATR threshold. This is not necessarily a bad trade decision, but the reason codes need to distinguish normal setup rejection from continuation setup acceptance.

6. Paper capital and position sizing can make trade numbers look small or large without proving edge.
   Increasing paper capital helps simulate bigger order sizes, but it does not improve expectancy. Profitability must come from better entries, exits, data reliability, and risk/reward behavior.

## Evidence From Recent Paper Trading

Observed exits included both winners and losers:

- WIPRO: approximately +INR 6,902.15
- CIPLA: approximately +INR 4,211.90
- AXISBANK: approximately +INR 2,362.50
- ITC: approximately +INR 1,039.60
- SHREECEM: approximately +INR 960.00
- INFY: approximately -INR 2,221.20
- RELIANCE: approximately -INR 476.00
- HCLTECH: approximately -INR 475.20
- MARUTI: approximately -INR 159.00

This proves the paper execution path is active, but it does not yet prove durable profitability.

## Current Important Runtime Settings

- `micro_scan_interval_seconds`: 90
- `micro_exit_check_interval_seconds`: 30
- `micro_max_hold_minutes`: 10
- `micro_reentry_cooldown_seconds`: 300
- `micro_max_candle_age_seconds`: 180
- `market_closed_poll_seconds`: 60
- `position_reconciliation_enabled`: true
- `run_startup_overnight_analysis`: false
- Trading mode: paper trading
- Oracle collector: live Breeze market data through `80.225.242.6`
- AWS runtime: ECS Fargate in `eu-west-2`

## Priority Actions

1. Verify market-open startup sleep fix in ECS logs after deploy.
2. Verify the separate 30-second exit monitor in ECS logs after deploy.
3. Verify startup position reconciliation closes stale paper snapshots and blocks unsafe live reconciliation.
4. Verify manual market-service startup logs show overnight analysis skipped.
5. Harden Oracle/Breeze collector retry, timeout, and stale-data handling.
6. Clarify continuation setup reason codes and thresholds.
7. Review 5-minute cooldown using paper evidence.
8. Add richer per-trade telemetry for expected R, realized R, entry reason, exit reason, and data quality.

## Live Trading Decision

Do not switch to real-money trading until the high-priority P12 items are implemented, deployed, and reviewed in paper mode. The system is moving in the right direction, but the current risks are operational and timing-related, which are exactly the kind of issues that can turn a good signal into a bad live trade.
