from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "market_intelligence_sources.md"
PLAN = ROOT / "PROJECT_PLAN.md"


def test_market_intelligence_source_audit_exists_and_covers_live_sources():
    text = DOC.read_text()

    required_phrases = [
        "Official NSE/BSE company announcements",
        "RBI and SEBI official/regulatory updates",
        "Broker/Oracle quote validation before live order placement",
        "Indian market news",
        "Global financial news",
        "Company-specific news",
        "M&A and corporate actions",
        "Social sentiment from X/Reddit",
        "Current source coverage is acceptable for paper-trading observation only.",
    ]

    for phrase in required_phrases:
        assert phrase in text


def test_market_intelligence_audit_maps_gaps_to_phase_10a_work_packages():
    text = DOC.read_text()

    for work_package in [
        "P10A-WP01",
        "P10A-WP02",
        "P10A-WP03",
        "P10A-WP04",
        "P10A-WP05",
        "P10A-WP06",
        "P10A-WP07",
        "P10A-WP08",
    ]:
        assert work_package in text


def test_project_plan_tracks_source_coverage_audit():
    plan = PLAN.read_text()

    assert "P10A-WP01 | Add source coverage audit |" in plan
    assert "docs/market_intelligence_sources.md" in plan
    assert "tests/unit/test_market_intelligence_sources.py" in plan
