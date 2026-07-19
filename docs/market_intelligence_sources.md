# Market Intelligence Source Coverage Audit

This document is the `P10A-WP01` source coverage audit for the Indian intraday trading system.

Purpose:

- Define the minimum market-intelligence source coverage needed before live trading.
- Separate paper-trading acceptable sources from live-readiness requirements.
- Record freshness, reliability, and fail-closed expectations for each source class.
- Make gaps explicit so later `P10A` work packages can implement them without changing the master plan.

## Readiness Summary

Current source coverage is acceptable for paper-trading observation only.

Live trading must not be enabled until official Indian corporate/regulatory feeds, source freshness checks, and signal-level source-quality gates are implemented.

| Source Class | Required For Live | Current Coverage | Current Status | Target Freshness | Required Behavior |
|---|---:|---|---|---|---|
| Global macro market prices | Yes | Yahoo Finance via `agent/overnight/global_macro.py` | Partially covered | Overnight before market open; refresh on runtime restart | Missing or stale macro data reduces confidence; do not simulate in production. |
| US/Europe/Asia index cues | Yes | Yahoo Finance indices | Partially covered | Overnight before market open | Missing data is visible in market state and signal reasons. |
| Commodities, DXY, yields, India VIX | Yes | Yahoo Finance tickers | Partially covered | Overnight before market open | Stale or missing risk proxies reduce confidence. |
| Indian market news | Yes | NewsAPI queries in `agent/overnight/news_aggregator.py` and `agent/tools/news_fetcher.py` | Partially covered | 5 to 15 minutes during market hours | Do not silently fall back to simulated news in production. |
| Global financial news | Yes | Some NewsAPI helper code exists; overnight runtime currently uses simulated global headlines | Gap | Overnight before market open; intraday for high-impact events | Real provider, RSS, or GDELT-backed global news required before live trading. |
| Company-specific news | Yes | NewsAPI query by symbol/company for a limited list | Partially covered | 15 minutes during market hours | Company headlines must be symbol-normalized, deduped, and visible in signal reasons. |
| NSE/BSE company announcements | Yes | Parser exists in `agent/data/company_announcements.py`; no official fetcher yet | Gap | 3 to 5 minutes during market hours; overnight catch-up | Results, dividends, board meetings, orders, penalties, M&A, buybacks, management changes must be official-source backed. |
| M&A and corporate actions | Yes | Keyword classification exists only after an announcement payload is provided | Gap | 3 to 5 minutes during market hours; overnight catch-up | Merger, acquisition, demerger, split, bonus, buyback, and scheme-of-arrangement events can block or reduce signal confidence. |
| RBI events | Yes | No dedicated ingestion | Gap | 5 minutes during market hours; overnight catch-up | Monetary policy, liquidity, bank regulation, circulars, and speeches are structured as regulatory events. |
| SEBI events | Yes | No dedicated ingestion | Gap | 5 minutes during market hours; overnight catch-up | Penalties, bans, circulars, market-structure changes, and enforcement events are structured as regulatory events. |
| Broker tradable quote validation | Yes | Market-data tools use Yahoo-style data; Oracle/Breeze execution path exists | Gap for final pre-order quote validation | Immediately before order placement | Live orders must validate tradable price/quote through broker/Oracle path before submission. |
| Social sentiment from X/Reddit | No | Config placeholders exist; `agent/specialists/social.py` returns neutral placeholder | Optional gap | 15 to 60 minutes if enabled | Social sentiment is advisory only and must not override official news, announcements, or risk gates. |
| Learning/performance feedback | Yes | Pattern analyzer and learning gates exist | Partially covered | End of day and before next market day | Learning cannot loosen thresholds without sample-size gates. |

## Source Priority

Tier 1 sources are required for live trading:

- Official NSE/BSE company announcements.
- RBI and SEBI official/regulatory updates.
- Broker/Oracle quote validation before live order placement.
- DynamoDB audit records for source freshness and signal reasons.

Tier 2 sources are required for signal quality but may use provider fallback:

- Indian market news.
- Global financial news.
- Global macro prices and risk proxies.
- Company-specific news.

Tier 3 sources are optional:

- X/Twitter sentiment.
- Reddit sentiment.
- Other retail/social chatter.

## Current Code Coverage

| Module | Current Use | Risk |
|---|---|---|
| `agent/overnight/global_macro.py` | Pulls US, Europe, Asia, India VIX, DXY, crude, gold, and yields from Yahoo Finance. | Useful but not authoritative; missing data currently degrades quietly. |
| `agent/overnight/news_aggregator.py` | Runs overnight and market-hours news scans. Real-time India, sector, and company queries use NewsAPI when configured. | Some overnight global/India paths still use simulated data. |
| `agent/tools/news_fetcher.py` | Fetches India, company, sector, and global news through NewsAPI with simulated fallback. | Simulated fallback is acceptable for tests but unsafe for production if silent. |
| `agent/data/company_announcements.py` | Normalizes announcement payloads into structured event features. | Parser exists, but no NSE/BSE source adapter feeds it yet. |
| `agent/signals/sentiment.py` | Combines global, Indian, company, and announcement sentiment scores. | Needs source-quality/freshness inputs and official event wiring. |
| `agent/specialists/social.py` | Returns neutral placeholder. | Safe because it does not pretend to be real data. |
| `agent/execution/oracle_breeze_client.py` | Sends signed order requests to Oracle execution proxy. | Execution path exists; final broker quote validation still needs an explicit live-readiness gate. |

## Required Future Work Mapping

| Gap | Owning Work Package |
|---|---|
| Official source coverage documented and kept under test | `P10A-WP01` |
| NSE/BSE announcement fetchers and fixtures | `P10A-WP02` |
| RBI/SEBI regulatory event fetchers and fixtures | `P10A-WP03` |
| Production news fallback, request limits, and no silent simulation | `P10A-WP04` |
| Source freshness/reliability scoring | `P10A-WP05` |
| Intelligence signals wired into decision reasons and blockers | `P10A-WP06` |
| Dashboard view of source health and event reasons | `P10A-WP07` |
| Replay against known high-impact event days | `P10A-WP08` |

## Live-Readiness Policy

Before `P10-WP03` can be marked tested:

- Each Tier 1 source must have an implementation or an explicit manual operational substitute.
- Simulated news must be disabled or visibly marked in production.
- Source freshness must be stored in DynamoDB and visible on the dashboard.
- A missing Tier 1 source must reduce confidence or block new live trades.
- Every final signal must include source-backed reasons for global news, Indian market news, company news, official announcements, regulatory events, and broker quote validation status.
