FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa && rm -rf /var/lib/apt/lists/*
WORKDIR /worker
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY worker.py ./
ENV PATH="/worker/.venv/bin:$PATH"
CMD ["python", "worker.py"]
