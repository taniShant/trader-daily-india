FROM python:3.12-slim

WORKDIR /app

COPY oracle/collector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY oracle/collector/app.py .

ENV PYTHONUNBUFFERED=1
ENV ORACLE_COLLECTOR_MODE=live
ENV ORACLE_STATIC_IP=80.225.242.6

EXPOSE 8090

CMD ["python", "-c", "import uvicorn; from app import app; uvicorn.run(app, host='0.0.0.0', port=8090)"]
