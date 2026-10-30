# Lightweight Python 3.11 base image
FROM python:3.11-slim

# Prevent Python from writing .pyc and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8765

WORKDIR /app

# Install minimal system dependencies for networking & healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code, frontend assets, and benchmark data
COPY src/ ./src/
COPY frontend/ ./frontend/
COPY files/ ./files/
COPY data/ ./data/

# Expose application port
EXPOSE 8765

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8765}/dashboard.html || exit 1

# Run the REST server
CMD ["python", "-m", "smartretail.server"]

