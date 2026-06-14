# ---------- Backend stage ----------
FROM python:3.12-slim AS backend
WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    tesseract-ocr tesseract-ocr-eng && \
    rm -rf /var/lib/apt/lists/*

# Cache Python deps (pip upgraded first — base-image pip has known CVEs)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy Python code
COPY ./app /app/app
COPY ./services /app/services
# Plugins whose code lives outside this repo (PLUGIN_PATHS — "repo split" prep,
# see external_plugins/README.md). Loaded the same way services/ plugins are.
COPY ./external_plugins /app/external_plugins

# Marketplace catalog (shipped copy; the Plugin Store also fetches a remote one)
COPY registry.json /app/registry.json

# Copy the **pre‑built** UI assets (now at the project root)
COPY ./dist ./static

ENV PYTHONPATH=/app
EXPOSE 8000
ENV AI_PROVIDER=ollama \
    OLLAMA_URL=http://localhost:11434 \
    OLLAMA_MODEL=llama3.2

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]