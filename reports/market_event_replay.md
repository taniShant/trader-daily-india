# Market Intelligence Event Replay

Phase 10A replays known high-impact market event shapes through the same source-quality, sentiment, and signal-scoring path used by the live agent.

Replay fixture: `tests/fixtures/market_events/known_event_days.json`

Current deterministic cases:

| Case | Purpose | Expected outcome |
| --- | --- | --- |
| `fresh-m-and-a-announcement` | Confirms fresh global, India, company, NSE/BSE-style announcement, and SEBI context can produce an explained actionable signal for `MARUTI`. | `BUY`, source quality not blocked, corporate-action category detected. |
| `missing-official-sources-block` | Confirms unavailable global news plus missing official announcements/regulatory feeds fail closed. | `HOLD`, confidence `0`, source-quality block reasons visible. |
| `sebi-enforcement-caution` | Confirms fresh SEBI enforcement and company regulatory disclosure are classified and visible in signal reasons. | `HOLD`, source quality not blocked, regulatory/enforcement categories detected. |

Validation command:

```bash
python -m pytest tests/unit/test_event_replay.py tests/unit/test_signal_intelligence_integration.py tests/unit/test_source_quality.py tests/unit/test_backtest_engine.py -q
```
