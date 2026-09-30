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
ARG AEGIS_DETECTION_MODEL_PATH=/app/models/yolo11n.pt
ENV AEGIS_DETECTION_MODEL_PATH=${AEGIS_DETECTION_MODEL_PATH}
ARG AEGIS_BENCHMARK_MODEL_NAMES="yolo26n.pt yolo26s.pt"
ENV AEGIS_BENCHMARK_MODEL_NAMES=${AEGIS_BENCHMARK_MODEL_NAMES}
ARG AEGIS_THREAT_MODEL_PATH=/app/models/yoloe-26n-seg.pt
ENV AEGIS_THREAT_MODEL_PATH=${AEGIS_THREAT_MODEL_PATH}
ARG AEGIS_THREAT_PROMPT_EMBEDDINGS_PATH=/app/models/yoloe-26n-seg.threat-prompts.npz
ENV AEGIS_THREAT_PROMPT_EMBEDDINGS_PATH=${AEGIS_THREAT_PROMPT_EMBEDDINGS_PATH}
ARG AEGIS_THREAT_BENCHMARK_MODEL_NAMES="yoloe-26n-seg.pt yoloe-26s-seg.pt"
ENV AEGIS_THREAT_BENCHMARK_MODEL_NAMES=${AEGIS_THREAT_BENCHMARK_MODEL_NAMES}
ENV AEGIS_THREAT_CLASSES_JSON='["handgun","pistol","revolver","rifle","shotgun","knife","machete","baseball bat","crowbar"]'

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
    git \
    || (sleep 5 && apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1) \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# YOLOE needs this tokenizer only while prompt embeddings are generated during
# the image build. Runtime loads those persisted embeddings and never prompts.
RUN pip install --no-cache-dir git+https://github.com/ultralytics/CLIP.git@a13192f8cb767260d7dfd98c843b0716593169e7

# Copy application code
COPY --chown=aegis:aegis . .

# Provision the configured detector and explicitly named benchmark candidates
# at image-build time. Application runtime only accepts local checkpoints and
# never downloads or substitutes one.
RUN mkdir -p /app/models && \
    python scripts/provision_vision_models.py && \
    chown -R aegis:aegis /app/models

# Create data directories
RUN mkdir -p /app/data/input /app/data/output && \
    chown -R aegis:aegis /app/data

# Switch to non-root user
USER aegis

# Expose API port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')" || exit 1

# Default command - API server only
CMD ["python", "-m", "uvicorn", "aegis.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
