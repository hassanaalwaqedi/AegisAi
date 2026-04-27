# AegisAI Docker Build
FROM python:3.10-slim

# Set labels
LABEL maintainer="AegisAI Team"
LABEL description="Smart City Risk Intelligence System"
LABEL version="4.1.0"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV AEGIS_DEBUG=false
ENV AEGIS_API_HOST=0.0.0.0
ENV AEGIS_API_PORT=8080
ENV YOLO_CONFIG_DIR=/tmp/Ultralytics

# Create non-root user
RUN groupadd --gid 1000 aegis && \
    useradd --uid 1000 --gid aegis --shell /bin/bash --create-home aegis

# Set working directory
WORKDIR /app

# Install system dependencies for OpenCV.
# Debian slim no longer ships libgl1-mesa-glx in newer releases.
RUN apt-get update --fix-missing \
    && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    || (sleep 5 && apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1) \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=aegis:aegis . .

# Preload the default model used by the API detection route.
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" && \
    chown aegis:aegis /app/yolov8n.pt

# Create data directories
RUN mkdir -p /app/data/input /app/data/output && \
    chown -R aegis:aegis /app/data

# Switch to non-root user
USER aegis

# Expose API port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/')" || exit 1

# Default command - API server only
CMD ["python", "-m", "uvicorn", "aegis.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
