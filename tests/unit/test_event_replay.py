from pathlib import Path

from agent.backtest.event_replay import load_event_replay_cases, run_event_replay
from agent.contracts.signals import SignalAction


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "market_events" / "known_event_days.json"


def test_load_event_replay_cases_from_fixture():
    cases = load_event_replay_cases(FIXTURE)

    assert [case.case_id for case in cases] == [
        "fresh-m-and-a-announcement",
        "missing-official-sources-block",
        "sebi-enforcement-caution",
    ]
    assert cases[0].symbol == "MARUTI"


def test_event_replay_detects_official_events_and_expected_actions():
    report = run_event_replay(load_event_replay_cases(FIXTURE))

    assert report.passed is True
    by_case = {finding.case_id: finding for finding in report.findings}
    maruti = by_case["fresh-m-and-a-announcement"]
    assert maruti.signal.action == SignalAction.BUY
    assert maruti.source_quality.live_trade_blocked is False
    assert {str(item.category) for item in maruti.announcements} == {"corporate_action"}
    assert {str(item.category) for item in maruti.regulatory_events} == {"market_structure"}


def test_event_replay_blocks_when_sources_are_unavailable_or_missing():
    report = run_event_replay(load_event_replay_cases(FIXTURE))
    blocked = {finding.case_id: finding for finding in report.findings}["missing-official-sources-block"]

    assert blocked.signal.action == SignalAction.HOLD
    assert blocked.signal.confidence == 0
    assert blocked.source_quality.live_trade_blocked is True
    assert "source_quality_block" in blocked.signal.reasons
    assert "missing official announcements" in blocked.signal.reasons
    assert "missing regulatory events" in blocked.signal.reasons


def test_event_replay_report_is_markdown_ready():
    report = run_event_replay(load_event_replay_cases(FIXTURE))
    markdown = report.to_markdown()

    assert "# Market Intelligence Event Replay" in markdown
    assert "| fresh-m-and-a-announcement | MARUTI | BUY |" in markdown
    assert "| missing-official-sources-block | RELIANCE | HOLD |" in markdown
