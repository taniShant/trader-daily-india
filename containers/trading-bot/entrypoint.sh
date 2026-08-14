#!/bin/bash
set -e

echo "🤖 Trading Bot Container Starting..."
echo "📅 Market hours: 9:15 AM - 3:30 PM IST"
echo "⏱️  Analysis interval: ${ANALYSIS_INTERVAL_SECONDS:-180} seconds"
echo "⏳ Market closed poll: ${MARKET_CLOSED_POLL_SECONDS:-60} seconds"
echo "⚡ Micro exit check interval: ${MICRO_EXIT_CHECK_INTERVAL_SECONDS:-30} seconds"
echo "🌙 Startup overnight analysis: ${RUN_STARTUP_OVERNIGHT_ANALYSIS:-false}"

# ============================================================
# VALIDATE REQUIRED SECRETS
# ============================================================

echo ""
echo "🔐 Validating secrets..."

MISSING_SECRETS=""
PAPER_MODE="${PAPER_TRADING:-true}"
PAPER_MODE="$(printf '%s' "$PAPER_MODE" | tr '[:upper:]' '[:lower:]')"

echo "   Paper Trading: ${PAPER_TRADING:-true}"
echo "   Execution boundary: Oracle proxy at ${ORACLE_EXECUTION_PROXY_BASE_URL:-not configured}"

if [ "$PAPER_MODE" = "true" ] || [ "$PAPER_MODE" = "1" ] || [ "$PAPER_MODE" = "yes" ] || [ "$PAPER_MODE" = "on" ]; then
    echo "✅ Paper mode enabled - ICICI credentials are not required in AWS"
else
    if [ -z "$ORACLE_EXECUTION_PROXY_BASE_URL" ]; then
        echo "❌ ORACLE_EXECUTION_PROXY_BASE_URL is not set"
        MISSING_SECRETS="$MISSING_SECRETS ORACLE_EXECUTION_PROXY_BASE_URL"
    else
        echo "✅ ORACLE_EXECUTION_PROXY_BASE_URL is set"
    fi

    if [ -z "$ORACLE_PROXY_SHARED_SECRET" ]; then
        echo "❌ ORACLE_PROXY_SHARED_SECRET is not set"
        MISSING_SECRETS="$MISSING_SECRETS ORACLE_PROXY_SHARED_SECRET"
    else
        echo "✅ ORACLE_PROXY_SHARED_SECRET is set"
    fi

    echo "ℹ️  ICICI credentials must remain on the Oracle static-IP proxy, not in AWS ECS"
fi

# NEWS_API_KEY is optional
if [ -z "$NEWS_API_KEY" ]; then
    echo "⚠️  NEWS_API_KEY is not set (news sentiment will be limited)"
else
    echo "✅ NEWS_API_KEY is set"
fi

# AWS credentials check
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "⚠️  AWS credentials not set - using IAM role (ECS Task Role)"
else
    echo "✅ AWS credentials are set"
fi

echo ""

# ============================================================
# ABORT IF CRITICAL SECRETS MISSING
# ============================================================

if [ -n "$MISSING_SECRETS" ]; then
    echo "❌ FATAL: Missing required secrets:$MISSING_SECRETS"
    echo "   Please ensure these secrets are passed to the ECS task."
    echo "   In paper mode no execution secret is required; in live mode AWS needs Oracle proxy signing credentials."
    exit 1
fi

echo "✅ All required secrets validated successfully"
echo ""

# ============================================================
# DISPLAY CONFIGURATION
# ============================================================

echo "📋 Trading Configuration:"
echo "   Environment: ${ENVIRONMENT:-dev}"
echo "   Paper Trading: ${PAPER_TRADING:-true}"
echo "   Capital: ₹${CAPITAL:-100000}"
echo "   Min Confidence: ${MIN_CONFIDENCE_THRESHOLD:-70}%"
echo "   Max Daily Loss: ${MAX_DAILY_LOSS_PERCENT:-4}%"
echo "   Max Position Size: ${MAX_POSITION_SIZE_PERCENT:-10}%"
echo "   Watchlist Size: ${WATCHLIST_SIZE:-10}"
echo "   Bedrock Default Model: ${BEDROCK_MODEL_ID:-anthropic.claude-3-7-sonnet-20250219-v1:0}"
echo "   Bedrock Fast Model: ${BEDROCK_FAST_MODEL_ID:-anthropic.claude-3-7-sonnet-20250219-v1:0}"
echo "   Bedrock Reasoning Model: ${BEDROCK_REASONING_MODEL_ID:-anthropic.claude-3-7-sonnet-20250219-v1:0}"
echo "   Bedrock Deep Research Model: ${BEDROCK_DEEP_RESEARCH_MODEL_ID:-anthropic.claude-opus-4-6-v1}"
echo "   Oracle Static IP: ${ORACLE_STATIC_IP:-${STATIC_IP:-80.225.242.6}}"
if [ -n "$SCHEDULED_ACTION" ]; then
    echo "   Scheduled Action: $SCHEDULED_ACTION"
    echo "   Run Source: ${RUN_SOURCE:-manual}"
fi
echo ""

# ============================================================
# RUN ONE-SHOT SCHEDULED ACTIONS
# ============================================================

if [ -n "$SCHEDULED_ACTION" ]; then
    echo "⏱️ Running scheduled action: $SCHEDULED_ACTION"

    exec python -c "
import os
import sys

action = os.environ.get('SCHEDULED_ACTION', '').strip().lower()
print(f'Scheduled action: {action}')

try:
    from agent.main import TradingBot

    bot = TradingBot()

    if action == 'overnight_analysis':
        bot._run_overnight_analysis()
    elif action == 'market_open':
        print('Market-open scheduled checkpoint completed. Singleton trading service remains authoritative.')
    elif action == 'square_off':
        bot._square_off_all()
    else:
        print(f'Unsupported scheduled action: {action}')
        sys.exit(2)

    print(f'Scheduled action completed: {action}')
except Exception as e:
    print(f'Scheduled action failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"
fi

# ============================================================
# START THE TRADING BOT
# ============================================================

echo "🚀 Starting Trading Bot..."

# Run the trading bot
exec python -c "
import os
import sys
import time
from datetime import datetime

print('=' * 60)
print('🤖 ECS Compatible Trading Bot Starting')
print('=' * 60)
print(f'AWS Region: {os.environ.get(\"AWS_REGION\", \"eu-west-2\")}')
print(f'Environment: {os.environ.get(\"ENVIRONMENT\", \"dev\")}')
print(f'Paper Trading: {os.environ.get(\"PAPER_TRADING\", \"true\")}')
print(f'Analysis Interval: {os.environ.get(\"ANALYSIS_INTERVAL_SECONDS\", \"180\")} seconds')
print(f'Market Closed Poll: {os.environ.get(\"MARKET_CLOSED_POLL_SECONDS\", \"60\")} seconds')
print(f'Micro Exit Check Interval: {os.environ.get(\"MICRO_EXIT_CHECK_INTERVAL_SECONDS\", \"30\")} seconds')
print(f'Position Reconciliation Enabled: {os.environ.get(\"POSITION_RECONCILIATION_ENABLED\", \"true\")}')
print(f'Startup Overnight Analysis: {os.environ.get(\"RUN_STARTUP_OVERNIGHT_ANALYSIS\", \"false\")}')
print(f'Capital: ₹{float(os.environ.get(\"CAPITAL\", 100000)):,.2f}')
print(f'Min Confidence: {os.environ.get(\"MIN_CONFIDENCE_THRESHOLD\", \"70\")}%')
print(f'Max Daily Loss: {os.environ.get(\"MAX_DAILY_LOSS_PERCENT\", \"4\")}%')
print(f'Max Position Size: {os.environ.get(\"MAX_POSITION_SIZE_PERCENT\", \"10\")}%')
print(f'Bedrock Default Model: {os.environ.get(\"BEDROCK_MODEL_ID\", \"anthropic.claude-3-7-sonnet-20250219-v1:0\")}')
print(f'Bedrock Fast Model: {os.environ.get(\"BEDROCK_FAST_MODEL_ID\", \"anthropic.claude-3-7-sonnet-20250219-v1:0\")}')
print(f'Bedrock Reasoning Model: {os.environ.get(\"BEDROCK_REASONING_MODEL_ID\", \"anthropic.claude-3-7-sonnet-20250219-v1:0\")}')
print(f'Bedrock Deep Research Model: {os.environ.get(\"BEDROCK_DEEP_RESEARCH_MODEL_ID\", \"anthropic.claude-opus-4-6-v1\")}')
print(f'Oracle Proxy: {os.environ.get(\"ORACLE_EXECUTION_PROXY_BASE_URL\", \"not configured\")}')
print(f'Oracle Proxy Shared Secret: {\"✓ Present\" if os.environ.get(\"ORACLE_PROXY_SHARED_SECRET\") else \"✗ Missing/Not required in paper\"}')
print(f'Sessions Table: {os.environ.get(\"SESSIONS_TABLE\", \"svc-trd-sessions-dev\")}')
print(f'Trades Table: {os.environ.get(\"TRADES_TABLE\", \"svc-trd-trades-dev\")}')
print(f'Learning Table: {os.environ.get(\"LEARNING_TABLE\", \"svc-trd-learning-dev\")}')
print(f'Market State Table: {os.environ.get(\"MARKET_STATE_TABLE\", \"svc-trd-market-state-dev\")}')
print('=' * 60)

try:
    from agent.main import TradingBot
    
    # Set up metrics server on port 9090
    try:
        from prometheus_client import start_http_server
        start_http_server(9090)
        print('✅ Metrics server started on port 9090')
    except ImportError:
        print('⚠️ Prometheus client not installed - metrics disabled')
    except Exception as e:
        print(f'⚠️ Failed to start metrics server: {e}')
    
    # Get configuration from environment
    capital = float(os.environ.get('CAPITAL', 100000))
    analysis_interval = int(os.environ.get('ANALYSIS_INTERVAL_SECONDS', 180))
    paper_trading = os.environ.get('PAPER_TRADING', 'true').lower() == 'true'
    min_confidence = int(os.environ.get('MIN_CONFIDENCE_THRESHOLD', 70))
    max_daily_loss_percent = float(os.environ.get('MAX_DAILY_LOSS_PERCENT', 4))
    max_position_size_percent = float(os.environ.get('MAX_POSITION_SIZE_PERCENT', 10))
    watchlist_size = int(os.environ.get('WATCHLIST_SIZE', 10))
    bedrock_model_id = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-7-sonnet-20250219-v1:0')
    bedrock_fast_model_id = os.environ.get('BEDROCK_FAST_MODEL_ID', 'anthropic.claude-3-7-sonnet-20250219-v1:0')
    bedrock_reasoning_model_id = os.environ.get('BEDROCK_REASONING_MODEL_ID', 'anthropic.claude-3-7-sonnet-20250219-v1:0')
    bedrock_deep_research_model_id = os.environ.get('BEDROCK_DEEP_RESEARCH_MODEL_ID', 'anthropic.claude-opus-4-6-v1')
    bedrock_region = os.environ.get('BEDROCK_REGION', 'eu-west-2')
    static_ip = os.environ.get('ORACLE_STATIC_IP') or os.environ.get('STATIC_IP', '80.225.242.6')
    
    print(f'💰 Trading Capital: ₹{capital:,.2f}')
    print(f'⏱️  Analysis Interval: {analysis_interval} seconds')
    print(f'📝 Paper Trading: {paper_trading}')
    print(f'🎯 Min Confidence: {min_confidence}%')
    print(f'🛡️ Max Daily Loss: {max_daily_loss_percent}%')
    print(f'📊 Max Position Size: {max_position_size_percent}%')
    print(f'👀 Watchlist Size: {watchlist_size}')
    print(f'🧠 Bedrock Default Model: {bedrock_model_id}')
    print(f'🧠 Bedrock Fast Model: {bedrock_fast_model_id}')
    print(f'🧠 Bedrock Reasoning Model: {bedrock_reasoning_model_id}')
    print(f'🧠 Bedrock Deep Research Model: {bedrock_deep_research_model_id}')
    print(f'🌐 Oracle Static IP: {static_ip}')
    print('')
    
    bot = TradingBot()
    
    print('🚀 Starting main trading loop...')
    bot.run()
    
except ImportError as e:
    print(f'❌ Failed to import agent module: {e}')
    print('   Check that agent/ directory is properly copied to the container')
    sys.exit(1)
except Exception as e:
    print(f'❌ Fatal error: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"
