from agent.execution.reconciliation import reconcile_positions


def test_reconcile_positions_returns_no_issues_when_quantities_match():
    issues = reconcile_positions(
        {"RELIANCE": {"quantity": 10}},
        [{"symbol": "RELIANCE", "quantity": 10}],
    )

    assert issues == []


def test_reconcile_positions_detects_mismatch_and_missing_sides():
    issues = reconcile_positions(
        {
            "RELIANCE": {"quantity": 10},
            "TCS": {"quantity": 5},
        },
        [
            {"symbol": "RELIANCE", "quantity": 8},
            {"stock_code": "INFY", "quantity": 3},
        ],
    )

    by_symbol = {issue.symbol: issue for issue in issues}

    assert by_symbol["RELIANCE"].issue_type == "quantity_mismatch"
    assert by_symbol["RELIANCE"].ledger_quantity == 10
    assert by_symbol["RELIANCE"].broker_quantity == 8
    assert by_symbol["TCS"].issue_type == "missing_at_broker"
    assert by_symbol["INFY"].issue_type == "missing_in_ledger"
