FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.lock .
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.lock

FROM node:22-bookworm-slim AS motion
WORKDIR /motion
COPY remotion/package*.json ./
RUN npm ci

FROM node:22-bookworm-slim AS tscaps
WORKDIR /tscaps
COPY tools/tscaps/package*.json ./
# Captions run in Chromium, not the native Node ONNX backend.
RUN npm ci --ignore-scripts --no-audit --no-fund && npm cache clean --force \
    && node -e "require('node:fs').rmSync('node_modules/onnxruntime-node/bin', {recursive:true, force:true})"

FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    melt \
    libmlt7 \
    tesseract-ocr \
    tesseract-ocr-eng \
    fonts-dejavu-core \
    chromium \
    nodejs \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY --from=builder /opt/venv /opt/venv
COPY --from=motion /motion/node_modules /app/remotion/node_modules
COPY remotion/ remotion/
ENV REMOTION_BROWSER_EXECUTABLE=/usr/bin/chromium REMOTION_CONCURRENCY=2

COPY tools/tscaps/ tools/tscaps/
COPY --from=tscaps /tscaps/node_modules /app/tools/tscaps/node_modules
ENV TSCAPS_CHROME=/usr/bin/chromium

COPY app/ app/
COPY brain/ brain/
COPY creative/ creative/
COPY engine/ engine/
COPY hermes/ hermes/
COPY logging_config.py request_context.py .
COPY scripts/ scripts/
COPY presets/ presets/
COPY alembic/ alembic/
COPY alembic.ini .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f -H "Host: ${ALLOWED_HOSTS%%,*}" http://127.0.0.1:8000/health || exit 1

CMD ["gunicorn", "app.main:app", \
     "-w", "4", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-b", "0.0.0.0:8000", \
     "--timeout", "300", \
     "--graceful-timeout", "30"]
