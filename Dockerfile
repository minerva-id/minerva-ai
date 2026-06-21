FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Production stage ---
FROM python:3.12-slim

# Security: run as non-root user
RUN groupadd -r minerva && useradd -r -g minerva -d /app -s /sbin/nologin minerva

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY src/ ./src/
COPY pyproject.toml .
COPY frontend/dist/ ./frontend/dist/

# Install the application package
RUN pip install --no-cache-dir .

# Create model directory
RUN mkdir -p /app/models && chown minerva:minerva /app/models

# Switch to non-root user
USER minerva

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')" || exit 1

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AGENT_MODE=paper

ENTRYPOINT ["python", "-m", "minerva.main"]
