# ==============================================================================
# DOCKERFILE — Backend FastAPI + LangGraph (Python 3.13 + uv)
# ==============================================================================
# Multi-stage build:
#   1. builder: instala dependencias con uv
#   2. runtime: imagen mínima con el venv compilado
# ==============================================================================

# ---- Stage 1: Builder ----
FROM python:3.13-slim AS builder

# Instalar uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copiar archivos de dependencias primero (cachear layer de instalación)
COPY pyproject.toml uv.lock .python-version ./

# Instalar dependencias en un venv dentro del proyecto
RUN uv sync --frozen --no-dev --no-install-project

# Copiar el código fuente
COPY app/ app/
COPY main.py .

# ---- Stage 2: Runtime ----
FROM python:3.13-slim AS runtime

# Evitar la descarga de Chromium por Puppeteer durante la instalación global de NPM
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true

# Dependencias del sistema para psycopg, Node.js y Chromium para Mermaid CLI
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpq5 \
    nodejs \
    npm \
    chromium \
    unzip \
    fonts-liberation \
    libgbm1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    tesseract-ocr \
    tesseract-ocr-spa \
    postgresql-client \
    libgl1 \
    libglib2.0-0 && \
    npm install -g @mermaid-js/mermaid-cli && \
    rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /app

# Copiar el venv compilado desde el builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app
COPY --from=builder /app/main.py /app/main.py

# Asegurar que el venv esté en el PATH
ENV PATH="/app/.venv/bin:$PATH"

# Puerto del servidor
EXPOSE 8000

# Comando de inicio
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
