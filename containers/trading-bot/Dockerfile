FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for pandas-ta and yfinance
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY containers/trading-bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared agent code
COPY agent/ ./agent/

# Copy trading bot specific entrypoint
COPY containers/trading-bot/entrypoint.sh .
RUN chmod +x entrypoint.sh

# Environment variables (overridden by ECS task definition)
ENV PYTHONUNBUFFERED=1
ENV AWS_REGION=eu-west-2
ENV MODE=live
ENV ANALYSIS_INTERVAL_SECONDS=180
ENV PAPER_TRADING=true
ENV CAPITAL=100000
ENV MIN_CONFIDENCE_THRESHOLD=70
ENV MAX_DAILY_LOSS_PERCENT=4
ENV MAX_POSITION_SIZE_PERCENT=10
ENV WATCHLIST_SIZE=10
ENV BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
ENV BEDROCK_REGION=eu-west-2

# Health check (trading bot exposes metrics endpoint)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:9090/health || exit 1

EXPOSE 9090

ENTRYPOINT ["./entrypoint.sh"]