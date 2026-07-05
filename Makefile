PYTHON ?= python
PYTEST ?= $(PYTHON) -m pytest

.PHONY: help test test-unit test-integration test-dashboard test-phase7 test-phase8 smoke synth deploy-path verify clean-pyc

help:
	@printf "%s\n" "Available targets:"
	@printf "%s\n" "  make test             Run all tests"
	@printf "%s\n" "  make test-unit        Run unit tests"
	@printf "%s\n" "  make test-integration Run integration tests"
	@printf "%s\n" "  make test-dashboard   Run dashboard API and health-path tests"
	@printf "%s\n" "  make test-phase7      Run storage/backtest/learning tests"
	@printf "%s\n" "  make test-phase8      Run dashboard phase tests"
	@printf "%s\n" "  make smoke            Compile critical Python entrypoints"
	@printf "%s\n" "  make synth            Verify CDK synthesis"
	@printf "%s\n" "  make deploy-path      Verify AWS/Oracle deployment boundary"
	@printf "%s\n" "  make verify           Run smoke, deploy-path, tests, and synth"

test:
	$(PYTEST) tests/ -q

test-unit:
	$(PYTEST) tests/unit/ -q

test-integration:
	$(PYTEST) tests/integration/ -q

test-dashboard:
	$(PYTEST) tests/integration/test_dashboard_api.py tests/unit/test_dashboard_health_paths.py -q

test-phase7:
	$(PYTEST) tests/unit/test_repositories.py tests/unit/test_backtest_engine.py tests/unit/test_costs.py tests/unit/test_backtest_metrics.py tests/unit/test_learning_gates.py -q

test-phase8:
	$(PYTEST) tests/integration/test_dashboard_api.py tests/unit/test_dashboard_health_paths.py -q

smoke:
	$(PYTHON) -m py_compile agent/main.py containers/dashboard/api_server.py oracle/execution-proxy/app.py oracle/collector/app.py

synth:
	bash scripts/verify_cdk_synth.sh

deploy-path:
	$(PYTHON) scripts/verify_deploy_path.py

verify: smoke deploy-path test synth

clean-pyc:
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
