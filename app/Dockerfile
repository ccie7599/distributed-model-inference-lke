FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install Python and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Install optimum for ONNX export
RUN pip3 install --no-cache-dir optimum[onnxruntime-gpu]

# Download and export BERT model to ONNX format
RUN mkdir -p /models/bert-base-uncased && \
    python3 -c "from optimum.onnxruntime import ORTModelForFeatureExtraction; \
    model = ORTModelForFeatureExtraction.from_pretrained('google-bert/bert-base-uncased', export=True); \
    model.save_pretrained('/models/bert-base-uncased')"

# Copy application code
COPY inference_server.py .

# Expose ports
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Run the server
CMD ["python3", "inference_server.py"]
