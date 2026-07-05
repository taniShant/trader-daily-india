# Trading System Execution Guide

Use this file with `PROJECT_PLAN.md`.

`PROJECT_PLAN.md` is the source of truth for architecture, phase order, work-package IDs, gates, and progress. This file explains how to execute work without drifting from that plan.

## Working Rule

For each work package:

1. Pick one ID from `PROJECT_PLAN.md`.
2. Implement only that scope.
3. Add or update focused tests.
4. Run the listed test command or an equivalent narrower command.
5. Update `PROJECT_PLAN.md` status and test evidence.
6. Add an `Execution Log` entry in `PROJECT_PLAN.md`.

Do not mark work as `Tested` without recording the test result.

## Current Code Reuse Strategy

Do not throw away the existing `agent/` tree.

Keep and refactor:

- `agent/main.py`: remains the AWS ECS trading bot entry point.
- `agent/specialists/`: keep technical, sentiment, fundamental, derivatives agents. Fill in `social.py` only if social sentiment remains a priority.
- `agent/overnight/`: keep global macro, news aggregation, and pre-market scanner.
- `agent/learning/`: keep pattern analysis and confidence adjustment, but gate it behind sample-size and paper/backtest evidence.
- `agent/tools/market_data.py`: keep as the starting adapter, then normalize its return contracts.
- `agent/tools/news_fetcher.py`: keep as a source adapter.
- `agent/tools/database.py`: keep initially, then move toward repository classes.
- `agent/tools/order_execution.py`: stop using it for AWS live execution after Oracle proxy is built. Live execution from AWS must call `agent/execution/oracle_breeze_client.py`.
- `mcp-servers/`: keep as optional/reference tooling unless explicitly wired into runtime.
- `src/trader.py`: prototype/reference only, not production runtime.

Known current issues to fix early:

- `containers/trading-bot/entrypoint.sh` imports `agent.main.ECSCompatibleBot`, but current `agent/main.py` defines `TradingBot`.
- Specialist constructors expect `memory` in several files, while `agent/main.py` instantiates them with only `model`.
- `agent/specialists/technical.py` expects dataframe-like historical data, while `agent/tools/market_data.py` returns dictionaries.
- AWS-side code currently contains direct Breeze execution; target design requires Oracle static-IP proxy for live execution.

## Target Runtime Boundaries

```text
AWS ECS Trading Bot
  -> data normalization
  -> deterministic features
  -> specialist analysis / LLM summaries
  -> signal scorer
  -> deterministic risk manager
  -> paper broker OR Oracle execution client

Oracle Execution Proxy
  -> signed request validation
  -> idempotency check
  -> Breeze API call from static IP
  -> response back to AWS
```

Oracle does not decide what to trade.

## Suggested Target Folders

Add these gradually around existing code:

```text
agent/
  config.py
  contracts/
    market.py
    signals.py
    execution.py
    risk.py
  data/
    symbols.py
    quality.py
    oracle_client.py
  signals/
    technical.py
    sentiment.py
    derivatives.py
    scorer.py
    llm_validation.py
  risk/
    manager.py
    rules.py
  execution/
    broker.py
    paper_broker.py
    oracle_breeze_client.py
    order_monitor.py
    position_monitor.py
    square_off.py
  storage/
    repositories.py
  time/
    market_clock.py
  backtest/
    engine.py
    costs.py
    metrics.py

oracle/
  execution-proxy/
    app.py
    auth.py
    breeze_client.py
    Dockerfile
    requirements.txt
  collector/
  terraform/ or scripts/

tests/
  unit/
  integration/
```

## First Implementation Sequence

Start here before adding more strategy logic:

1. `P0-WP02`: domain contracts.
2. `P0-WP03`: runtime import and constructor fixes.
3. `P0-WP04`: config loader.
4. `P1-WP01`: Oracle proxy health/mock skeleton.
5. `P1-WP02`: signed Oracle proxy requests.
6. `P3-WP02`: risk manager.
7. `P3-WP03`: paper broker.
8. `P3-WP04`: route AWS live execution through Oracle client only.

## Common Commands

## Environment Configuration

Use these files for environment-specific values:

- `cicd/env/prod.json`: source of truth for deployed production infrastructure values. `app.py` loads this when `CDK_DEPLOY_ENV=prod`.
- `cicd/env/dev.json`: optional future development environment config if a separate dev stack is needed.
- `.env`: local-only runtime overrides for Docker and local tests. Do not commit real `.env`.
- `.env.example`: template for local runtime variables.

Oracle static IP:

- Current Oracle static IP: `80.225.242.6`.
- Put deployed Oracle values under the `oracle` section in `cicd/env/prod.json`.
- Put local runtime overrides in `.env` using `ORACLE_STATIC_IP` and `ORACLE_EXECUTION_PROXY_BASE_URL`.

AWS remains the main system. Oracle is the static-IP execution boundary for ICICI Breeze.

AWS networking distinction:

- AWS NAT gateway IP in `cicd/env/prod.json`: `35.177.116.82`.
- Oracle/ICICI whitelisted static IP in `cicd/env/prod.json`: `80.225.242.6`.
- AWS NAT is for AWS private subnet egress only.
- Oracle static IP is the only ICICI Breeze live execution boundary.
- The CDK network stack exports `AwsNatGatewayIp` and `OracleStaticIp` separately.

EventBridge schedules:

- Runtime schedules are defined in `cicd/stacks/agent_runtime_stack.py`.
- Schedule expressions live in `cicd/env/prod.json` under `scheduled_tasks`.
- `overnight_analysis` runs as one private ECS Fargate task at 17:00 UTC on weekdays.
- `market_open` runs as one private ECS Fargate task at 03:45 UTC on weekdays.
- `square_off` runs as one private ECS Fargate task at 09:50 UTC on weekdays.
- Scheduled tasks set `SCHEDULED_ACTION` and exit after the one-shot action; they must not start another long-running trading loop.

## Active Deployment Path

P0-WP05 decision:

- AWS infrastructure and ECS services are owned by CDK: `app.py` and `cicd/stacks/*.py`.
- GitHub Actions deploys AWS by building/pushing the trading bot and dashboard images, validating the deploy path, then running `cdk synth` and `cdk deploy --all`.
- `.github/workflows/deploy.yml` is the active AWS deploy workflow.
- `.github/workflows/daily-trading.yml` is a guard only. It must not invoke AgentCore or place/analyze trades. Runtime schedules will be added through CDK/EventBridge in `P2-WP06`.
- `cicd/ecstasks_unused/*.json` remain legacy/reference templates for now. They are not the active deployment source.
- Oracle deployment is separate and will be added under `oracle/` in Phase 1. Oracle remains the only live ICICI Breeze static-IP boundary.

Validate this decision:

```bash
python scripts/verify_deploy_path.py
python -m pytest tests/unit/test_deploy_path.py -q
```

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Run tests:

```bash
python -m pytest tests/
```

Validate AWS CDK:

```bash
bash scripts/verify_cdk_synth.sh
```

The wrapper sets `CDK_DEPLOY_ENV=prod`, points CDK at the project `.venv`, and keeps jsii/CDK cache writes inside workspace-local ignored folders.

Build dashboard locally:

```bash
docker build -f containers/dashboard/Dockerfile -t trd-dashboard:local .
```

Build trading bot locally:

```bash
docker build -f containers/trading-bot/Dockerfile -t trd-bot:local .
```

Build Oracle execution proxy locally:

```bash
docker build -f oracle/execution-proxy/Dockerfile -t oracle-execution-proxy:local .
```

Run Oracle execution proxy locally in mock mode:

```bash
ORACLE_PROXY_MODE=mock ORACLE_STATIC_IP=80.225.242.6 uvicorn app:app --app-dir oracle/execution-proxy --host 0.0.0.0 --port 8080
```

Dry-run Oracle VM deployment:

```bash
oracle/scripts/deploy_execution_proxy.sh --dry-run
```

## Test Expectations By Area

Runtime:

- Config loads valid values.
- Bot can be imported in container-compatible mode.
- Specialist constructors work.
- Paper mode is default.

Risk:

- Daily loss breach blocks trades.
- Position size is capped.
- Duplicate order is blocked.
- New-trade cutoff is enforced.
- HOLD/skipped decisions are stored with reasons.

Storage/audit:

- Signals are stored in `SIGNALS_TABLE`.
- Risk approvals and rejections are stored in `RISK_EVENTS_TABLE`.
- Broker order requests and order status changes are stored in `ORDERS_TABLE`.
- Broker fills are stored in `FILLS_TABLE`.
- Open and closed intraday positions are stored in `POSITIONS_TABLE`.
- Existing session, trades, learning, and market-state tables remain available.
- CDK synth must expose the audit tables to both trading bot and dashboard ECS tasks.

Oracle proxy:

- `/health` works.
- `/ready` works in mock mode.
- `/mock/orders` accepts valid mock orders without calling Breeze.
- `/orders` requires signed request headers.
- Unsigned `/orders` requests fail.
- Expired `/orders` requests fail.
- Bad-signature `/orders` requests fail.
- Replayed `/orders` nonces fail safely.
- Valid signed `/orders` mock order succeeds.
- Breeze calls are isolated behind `oracle/execution-proxy/breeze_client.py`.
- Breeze client tests use fakes/mocks; no unit test should place a real order.
- Reusing the same `client_order_id` with the same order payload must not call execution twice.
- Reusing the same `client_order_id` with a different order payload must be rejected.
- Oracle VM deployment script supports `--dry-run` and defaults to static IP `80.225.242.6`.
- AWS-side `OracleBreezeClient` can place a signed mock order through the Oracle proxy integration test.

Execution:

- Paper broker never calls Oracle or Breeze.
- AWS live broker calls Oracle client only.
- Oracle proxy is the only component that calls Breeze live.
- Order/fill states are persisted.

Dashboard:

- `/` returns the app.
- `/api/health` returns healthy.
- Mode, heartbeat, P&L, positions, signals, skipped trades, and risk usage are visible.
- Manual controls call backend safety endpoints, not Breeze directly.

Backtesting:

- No lookahead.
- Slippage and costs included.
- Metrics include win rate, expectancy, drawdown, profit factor, and consecutive losses.

## Definition Of Done For Any Work Package

- Code is implemented in the planned boundary.
- Unit tests or integration tests are added/updated.
- Tests are run and result is recorded.
- `PROJECT_PLAN.md` tracker is updated.
- `PROJECT_PLAN.md` execution log has an entry.
