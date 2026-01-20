#!/usr/bin/env python3
"""
BERT ONNX Inference Server with Prometheus Metrics

A FastAPI-based inference server that exposes custom Prometheus metrics
for monitoring BERT model inference performance.
"""

import os
import time
from contextlib import asynccontextmanager
from typing import Optional

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel
from transformers import BertTokenizer

# Configuration from environment
MODEL_PATH = os.getenv("MODEL_PATH", "/models/bert-base-uncased/model.onnx")
# Also check for optimum-exported model path
if not os.path.exists(MODEL_PATH):
    alt_path = "/models/bert-base-uncased/model.onnx"
    if os.path.exists(alt_path):
        MODEL_PATH = alt_path
MAX_SEQUENCE_LENGTH = int(os.getenv("MAX_SEQUENCE_LENGTH", "512"))
EXECUTION_PROVIDER = os.getenv("ONNX_EXECUTION_PROVIDER", "CUDAExecutionProvider")


# Prometheus Metrics
REQUEST_COUNT = Counter(
    "inference_requests_total",
    "Total number of inference requests",
    ["status", "model"]
)

REQUEST_LATENCY = Histogram(
    "inference_request_duration_seconds",
    "Inference request latency in seconds",
    ["model"],
    buckets=[0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0]
)

TOKENS_PROCESSED = Counter(
    "inference_tokens_processed_total",
    "Total number of tokens processed",
    ["model"]
)

BATCH_SIZE = Histogram(
    "inference_batch_size",
    "Distribution of batch sizes",
    ["model"],
    buckets=[1, 2, 4, 8, 16, 32, 64]
)

MODEL_LOAD_TIME = Gauge(
    "inference_model_load_seconds",
    "Time taken to load the model",
    ["model"]
)

ACTIVE_REQUESTS = Gauge(
    "inference_active_requests",
    "Number of currently active inference requests",
    ["model"]
)

GPU_MEMORY_USED = Gauge(
    "inference_gpu_memory_bytes",
    "GPU memory used by the model",
    ["model", "device"]
)

QUEUE_SIZE = Gauge(
    "inference_queue_size",
    "Number of requests waiting in queue",
    ["model"]
)


class InferenceRequest(BaseModel):
    """Request model for inference endpoint."""
    text: Optional[str] = None
    texts: Optional[list[str]] = None
    inputs: Optional[dict] = None  # Pre-tokenized inputs
    include_embeddings: bool = False  # Set True to return full 512x768 embeddings (~8MB)


class InferenceResponse(BaseModel):
    """Response model for inference endpoint."""
    embeddings: Optional[list] = None
    pooler_output: Optional[list] = None
    latency_ms: float
    batch_size: int
    tokens_processed: int


class BertInferenceEngine:
    """BERT ONNX inference engine with metrics instrumentation."""

    def __init__(self, model_path: str, execution_provider: str = "CUDAExecutionProvider"):
        self.model_path = model_path
        self.model_name = "bert-base-uncased"
        self.tokenizer = None
        self.session = None
        self.execution_provider = execution_provider

    def load(self):
        """Load the ONNX model and tokenizer."""
        start_time = time.time()

        # Load tokenizer
        self.tokenizer = BertTokenizer.from_pretrained("google-bert/bert-base-uncased")

        # Configure ONNX Runtime session
        providers = []
        if self.execution_provider == "CUDAExecutionProvider":
            providers = [
                ("CUDAExecutionProvider", {
                    "device_id": 0,
                    "arena_extend_strategy": "kNextPowerOfTwo",
                    "gpu_mem_limit": 4 * 1024 * 1024 * 1024,  # 4GB
                    "cudnn_conv_algo_search": "EXHAUSTIVE",
                }),
                "CPUExecutionProvider"
            ]
        else:
            providers = ["CPUExecutionProvider"]

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = int(os.getenv("ONNX_INTRA_OP_THREADS", "4"))
        sess_options.inter_op_num_threads = int(os.getenv("ONNX_INTER_OP_THREADS", "2"))

        # Load model
        if os.path.exists(self.model_path):
            self.session = ort.InferenceSession(
                self.model_path,
                sess_options=sess_options,
                providers=providers
            )
        else:
            # For demo purposes, we'll create a mock session
            print(f"Warning: Model not found at {self.model_path}, running in mock mode")
            self.session = None

        load_time = time.time() - start_time
        MODEL_LOAD_TIME.labels(model=self.model_name).set(load_time)
        print(f"Model loaded in {load_time:.2f}s")

    def tokenize(self, texts: list[str], max_length: int = MAX_SEQUENCE_LENGTH) -> dict:
        """Tokenize input texts."""
        encoded = self.tokenizer(
            texts,
            padding="max_length",
            truncation=True,
            max_length=max_length,
            return_tensors="np"
        )
        return {
            "input_ids": encoded["input_ids"].astype(np.int64),
            "attention_mask": encoded["attention_mask"].astype(np.int64),
            "token_type_ids": encoded["token_type_ids"].astype(np.int64)
        }

    def infer(self, inputs: dict) -> dict:
        """Run inference on tokenized inputs."""
        ACTIVE_REQUESTS.labels(model=self.model_name).inc()

        try:
            start_time = time.time()

            # Get batch size and token count
            batch_size = len(inputs["input_ids"])
            tokens = int(np.sum(inputs["attention_mask"]))

            if self.session:
                # Run actual inference
                outputs = self.session.run(
                    None,
                    {
                        "input_ids": inputs["input_ids"],
                        "attention_mask": inputs["attention_mask"],
                        "token_type_ids": inputs["token_type_ids"]
                    }
                )
                result = {
                    "last_hidden_state": outputs[0].tolist(),
                    "pooler_output": outputs[1].tolist() if len(outputs) > 1 else None
                }
            else:
                # Mock inference for demo
                time.sleep(0.05)  # Simulate inference time
                result = {
                    "last_hidden_state": np.random.randn(batch_size, MAX_SEQUENCE_LENGTH, 768).tolist(),
                    "pooler_output": np.random.randn(batch_size, 768).tolist()
                }

            latency = time.time() - start_time

            # Record metrics
            REQUEST_COUNT.labels(status="success", model=self.model_name).inc()
            REQUEST_LATENCY.labels(model=self.model_name).observe(latency)
            TOKENS_PROCESSED.labels(model=self.model_name).inc(tokens)
            BATCH_SIZE.labels(model=self.model_name).observe(batch_size)

            return {
                **result,
                "latency_ms": latency * 1000,
                "batch_size": batch_size,
                "tokens_processed": tokens
            }

        except Exception as e:
            REQUEST_COUNT.labels(status="error", model=self.model_name).inc()
            raise e

        finally:
            ACTIVE_REQUESTS.labels(model=self.model_name).dec()


# Global inference engine
engine: Optional[BertInferenceEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for model loading."""
    global engine
    engine = BertInferenceEngine(MODEL_PATH, EXECUTION_PROVIDER)
    engine.load()
    yield
    # Cleanup if needed
    engine = None


# FastAPI app
app = FastAPI(
    title="BERT ONNX Inference Server",
    description="BERT inference with Prometheus metrics",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for demo page
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "model_loaded": engine is not None and engine.session is not None}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Prometheus metrics endpoint."""
    return PlainTextResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


@app.get("/v1/models/bert")
async def model_info():
    """Model metadata endpoint."""
    return {
        "name": "bert-base-uncased",
        "version": "1.0",
        "framework": "onnx",
        "execution_provider": EXECUTION_PROVIDER,
        "max_sequence_length": MAX_SEQUENCE_LENGTH
    }


@app.post("/v1/models/bert:predict", response_model=InferenceResponse)
async def predict(request: InferenceRequest):
    """Inference endpoint."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    # Handle different input formats
    if request.inputs:
        # Pre-tokenized inputs
        inputs = {
            "input_ids": np.array(request.inputs["input_ids"], dtype=np.int64),
            "attention_mask": np.array(request.inputs["attention_mask"], dtype=np.int64),
            "token_type_ids": np.array(request.inputs["token_type_ids"], dtype=np.int64)
        }
    elif request.texts:
        # Batch of texts
        inputs = engine.tokenize(request.texts)
    elif request.text:
        # Single text
        inputs = engine.tokenize([request.text])
    else:
        raise HTTPException(status_code=400, detail="No input provided")

    result = engine.infer(inputs)

    return InferenceResponse(
        embeddings=result.get("last_hidden_state") if request.include_embeddings else None,
        pooler_output=result.get("pooler_output"),
        latency_ms=result["latency_ms"],
        batch_size=result["batch_size"],
        tokens_processed=result["tokens_processed"]
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("SERVER_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVER_PORT", "8080")),
        workers=int(os.getenv("SERVER_WORKERS", "1"))
    )
