FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY containers/dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy dashboard code
COPY containers/dashboard/api_server.py .
COPY containers/dashboard/index.html .
COPY containers/dashboard/static/ ./static/

# Copy shared agent code (for data models only)
COPY agent/ ./agent/

# Environment variables (overridden by ECS task definition)
ENV PYTHONUNBUFFERED=1
ENV AWS_REGION=eu-west-2
ENV PORT=8080
ENV TRADES_TABLE=svc-trd-trades-dev
ENV LEARNING_TABLE=svc-trd-learning-dev
ENV MARKET_STATE_TABLE=svc-trd-market-state-dev
ENV SIGNALS_TABLE=svc-trd-signals-dev
ENV RISK_EVENTS_TABLE=svc-trd-risk-events-dev
ENV ORDERS_TABLE=svc-trd-orders-dev
ENV FILLS_TABLE=svc-trd-fills-dev
ENV POSITIONS_TABLE=svc-trd-positions-dev

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

EXPOSE 8080

CMD ["sh", "-c", "python -c \"import uvicorn; from api_server import app; uvicorn.run(app, host='0.0.0.0', port=8080)\""]
