FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ORACLE_PROXY_MODE=mock
ENV ORACLE_STATIC_IP=80.225.242.6
ENV PORT=8080

WORKDIR /app

COPY execution-proxy/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY execution-proxy/app.py ./app.py
COPY execution-proxy/auth.py ./auth.py
COPY execution-proxy/breeze_client.py ./breeze_client.py
COPY execution-proxy/idempotency.py ./idempotency.py

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
