# Backend image: FastAPI + deterministic rule engine + OCR (RapidOCR/PyMuPDF) +
# report generation. Used by Render (or any Docker host).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production

# System libraries required by onnxruntime / OpenCV (used by RapidOCR).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the package with all production extras (Postgres, storage, AI, OCR, report).
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install ".[all]"

EXPOSE 8000

# Render (and most PaaS) inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
