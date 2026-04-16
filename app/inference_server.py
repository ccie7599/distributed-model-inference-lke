#!/usr/bin/env python3
"""
BERT ONNX Inference Server with Prometheus Metrics and OpenTelemetry Tracing

A FastAPI-based inference server that exposes custom Prometheus metrics
and distributed tracing for monitoring BERT model inference performance.
"""

import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, HTTPException, Request
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

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.trace import Status, StatusCode

# Initialize OpenTelemetry Tracing
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "bert-inference")
OTEL_RESOURCE_ATTRS = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")

# Parse resource attributes
resource_attrs = {"service.name": SERVICE_NAME}
if OTEL_RESOURCE_ATTRS:
    for attr in OTEL_RESOURCE_ATTRS.split(","):
        if "=" in attr:
            key, value = attr.split("=", 1)
            resource_attrs[key] = value

resource = Resource.create(resource_attrs)
provider = TracerProvider(resource=resource)
otlp_exporter = OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True)
provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(provider)

# Get tracer for manual instrumentation
tracer = trace.get_tracer(__name__)

# Query-string token auth
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")
AUTH_OPEN_PATHS = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc"}

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

# Personalization Metrics
CLASSIFY_COUNT = Counter(
    "classify_requests_total",
    "Total mortgage classification requests",
    ["status"]
)

CLASSIFY_LATENCY = Histogram(
    "classify_request_duration_seconds",
    "Classification request latency in seconds",
    buckets=[0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0, 2.5]
)

MATCH_COUNT = Counter(
    "match_requests_total",
    "Total borrower match requests",
    ["status"]
)

MATCH_LATENCY = Histogram(
    "match_request_duration_seconds",
    "Borrower match request latency in seconds",
    buckets=[0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0, 2.5]
)

TOP_PRODUCT = Counter(
    "classify_top_product_total",
    "Count of each product recommended as top choice",
    ["product"]
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


class ClassifyRequest(BaseModel):
    """Request model for mortgage product classification."""
    text: str


class ProductRecommendation(BaseModel):
    """A single mortgage product recommendation."""
    product: str
    product_id: str
    confidence: float
    description: str
    highlights: list[str]
    min_credit_score: int
    min_down_payment_pct: float


class ClassifyResponse(BaseModel):
    """Response model for classification endpoint."""
    recommendations: list[ProductRecommendation]
    latency_ms: float


class MatchRequest(BaseModel):
    """Request model for borrower profile matching."""
    text: str
    top_k: int = 5


class BorrowerMatch(BaseModel):
    """A single borrower profile match."""
    profile: dict
    similarity: float


class MatchResponse(BaseModel):
    """Response model for matching endpoint."""
    matches: list[BorrowerMatch]
    latency_ms: float


class GeoPoint(BaseModel):
    """Geographic point with metadata."""
    lat: float
    lon: float
    city: str
    region: Optional[str] = None
    label: str


class NetworkInfoResponse(BaseModel):
    """Response for /v1/network-info — network topology for edge map."""
    compute: GeoPoint
    via_cdn: bool = False
    client_ip: Optional[str] = None


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

        # Create a span for the inference operation
        with tracer.start_as_current_span("bert.inference") as span:
            try:
                start_time = time.time()

                # Get batch size and token count
                batch_size = len(inputs["input_ids"])
                tokens = int(np.sum(inputs["attention_mask"]))

                # Add span attributes
                span.set_attribute("model.name", self.model_name)
                span.set_attribute("inference.batch_size", batch_size)
                span.set_attribute("inference.tokens", tokens)
                span.set_attribute("inference.execution_provider", self.execution_provider)

                if self.session:
                    # Run actual inference with nested span
                    with tracer.start_as_current_span("onnx.session.run") as onnx_span:
                        onnx_span.set_attribute("onnx.provider", self.execution_provider)
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
                    with tracer.start_as_current_span("mock.inference") as mock_span:
                        mock_span.set_attribute("mock", True)
                        time.sleep(0.05)  # Simulate inference time
                    result = {
                        "last_hidden_state": np.random.randn(batch_size, MAX_SEQUENCE_LENGTH, 768).tolist(),
                        "pooler_output": np.random.randn(batch_size, 768).tolist()
                    }

                latency = time.time() - start_time

                # Add latency to span
                span.set_attribute("inference.latency_ms", latency * 1000)

                # Record metrics
                REQUEST_COUNT.labels(status="success", model=self.model_name).inc()
                REQUEST_LATENCY.labels(model=self.model_name).observe(latency)
                TOKENS_PROCESSED.labels(model=self.model_name).inc(tokens)
                BATCH_SIZE.labels(model=self.model_name).observe(batch_size)

                span.set_status(Status(StatusCode.OK))

                return {
                    **result,
                    "latency_ms": latency * 1000,
                    "batch_size": batch_size,
                    "tokens_processed": tokens
                }

            except Exception as e:
                REQUEST_COUNT.labels(status="error", model=self.model_name).inc()
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise e

            finally:
                ACTIVE_REQUESTS.labels(model=self.model_name).dec()

    def get_embedding(self, text: str) -> np.ndarray:
        """Get 768-dim CLS embedding as raw numpy. No metrics recorded."""
        inputs = self.tokenize([text])
        if self.session:
            outputs = self.session.run(
                None,
                {
                    "input_ids": inputs["input_ids"],
                    "attention_mask": inputs["attention_mask"],
                    "token_type_ids": inputs["token_type_ids"]
                }
            )
            # Use pooler_output if available, otherwise CLS token from last_hidden_state
            if len(outputs) > 1:
                return outputs[1][0]
            return outputs[0][0][0]  # last_hidden_state[batch=0][token=0] (CLS)
        else:
            return np.random.randn(768).astype(np.float32)


class PersonalizationEngine:
    """Zero-shot classification and profile matching using BERT embeddings."""

    def __init__(self, inference_engine: BertInferenceEngine, data_dir: str):
        self.engine = inference_engine
        self.data_dir = Path(data_dir)
        self.products = []
        self.product_embeddings = None  # shape: (N_products, 768)
        self.profiles = []
        self.profile_embeddings = None  # shape: (N_profiles, 768)

    @property
    def profile_count(self) -> int:
        return len(self.profiles)

    def load(self):
        """Load product/profile data and pre-compute embeddings."""
        # Load mortgage products
        products_path = self.data_dir / "mortgage_products.json"
        with open(products_path) as f:
            data = json.load(f)
        self.products = data["products"]

        print(f"Computing embeddings for {len(self.products)} mortgage products...")
        product_embs = []
        for p in self.products:
            emb = self.engine.get_embedding(p["description"])
            product_embs.append(emb)
        self.product_embeddings = np.stack(product_embs)

        # Load borrower profiles
        profiles_path = self.data_dir / "borrower_profiles.json"
        with open(profiles_path) as f:
            data = json.load(f)
        self.profiles = data["profiles"]

        print(f"Computing embeddings for {len(self.profiles)} borrower profiles...")
        profile_embs = []
        for p in self.profiles:
            emb = self.engine.get_embedding(p["description"])
            profile_embs.append(emb)
        self.profile_embeddings = np.stack(profile_embs)

        print("Personalization engine ready")

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Cosine similarity between vector a (768,) and matrix b (N, 768) -> (N,)."""
        a_norm = a / (np.linalg.norm(a) + 1e-8)
        b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-8)
        return np.dot(b_norm, a_norm)

    def _softmax(self, x: np.ndarray, temperature: float = 0.1) -> np.ndarray:
        """Temperature-scaled softmax for confidence scores."""
        scaled = x / temperature
        exp_s = np.exp(scaled - np.max(scaled))
        return exp_s / exp_s.sum()

    def classify(self, text: str) -> dict:
        """Classify borrower text into mortgage product recommendations."""
        embedding = self.engine.get_embedding(text)
        similarities = self._cosine_similarity(embedding, self.product_embeddings)
        confidences = self._softmax(similarities)

        # Sort by confidence descending
        ranked_indices = np.argsort(confidences)[::-1]

        recommendations = []
        for idx in ranked_indices:
            p = self.products[idx]
            recommendations.append({
                "product": p["name"],
                "product_id": p["id"],
                "confidence": round(float(confidences[idx]), 4),
                "description": p["description"],
                "highlights": p["highlights"],
                "min_credit_score": p["min_credit_score"],
                "min_down_payment_pct": p["min_down_payment_pct"],
            })

        return {"recommendations": recommendations}

    def match(self, text: str, top_k: int = 5) -> dict:
        """Find similar borrower profiles."""
        embedding = self.engine.get_embedding(text)
        similarities = self._cosine_similarity(embedding, self.profile_embeddings)

        # Top-K by similarity
        top_k = min(top_k, len(self.profiles))
        top_indices = np.argsort(similarities)[::-1][:top_k]

        matches = []
        for idx in top_indices:
            p = self.profiles[idx]
            matches.append({
                "profile": {
                    "id": p["id"],
                    "name": p["name"],
                    "description": p["description"],
                    "mortgage_product": p["mortgage_product"],
                    "loan_amount": p["loan_amount"],
                    "rate": p["rate"],
                    "term_years": p["term_years"],
                    "outcome": p["outcome"],
                    "location": p["location"],
                },
                "similarity": round(float(similarities[idx]), 4),
            })

        return {"matches": matches}


# Global engines
engine: Optional[BertInferenceEngine] = None
personalization: Optional[PersonalizationEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for model loading."""
    global engine, personalization
    engine = BertInferenceEngine(MODEL_PATH, EXECUTION_PROVIDER)
    engine.load()

    data_dir = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
    if os.path.isdir(data_dir):
        personalization = PersonalizationEngine(engine, data_dir)
        personalization.load()
    else:
        print(f"Warning: Data directory not found at {data_dir}, personalization disabled")

    yield
    engine = None
    personalization = None


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
    expose_headers=["*"],
)

# Query-string token auth middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class TokenAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if AUTH_TOKEN and request.url.path not in AUTH_OPEN_PATHS:
            token = request.query_params.get("auth", "")
            if token != AUTH_TOKEN:
                return JSONResponse(status_code=403, content={"error": "forbidden"})
        return await call_next(request)


if AUTH_TOKEN:
    app.add_middleware(TokenAuthMiddleware)
    print(f"Token auth enabled (token length: {len(AUTH_TOKEN)})")
else:
    print("WARNING: AUTH_TOKEN not set — all endpoints are open")

# Instrument FastAPI with OpenTelemetry
FastAPIInstrumentor.instrument_app(app)


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
        "max_sequence_length": MAX_SEQUENCE_LENGTH,
        "features": ["embedding", "classify", "match"],
        "mortgage_products": len(personalization.products) if personalization else 0,
        "borrower_profiles": personalization.profile_count if personalization else 0,
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


@app.post("/v1/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    """Mortgage product classification via BERT embedding similarity."""
    if personalization is None:
        raise HTTPException(status_code=503, detail="Personalization engine not loaded")

    with tracer.start_as_current_span("mortgage.classify") as span:
        start_time = time.time()
        try:
            span.set_attribute("input.length", len(request.text))
            result = personalization.classify(request.text)
            latency = time.time() - start_time

            top = result["recommendations"][0]
            CLASSIFY_COUNT.labels(status="success").inc()
            CLASSIFY_LATENCY.observe(latency)
            TOP_PRODUCT.labels(product=top["product_id"]).inc()
            span.set_attribute("top_product", top["product_id"])
            span.set_attribute("top_confidence", top["confidence"])
            span.set_status(Status(StatusCode.OK))

            return ClassifyResponse(
                recommendations=result["recommendations"],
                latency_ms=latency * 1000
            )
        except Exception as e:
            CLASSIFY_COUNT.labels(status="error").inc()
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/match", response_model=MatchResponse)
async def match(request: MatchRequest):
    """Borrower profile matching via BERT embedding similarity."""
    if personalization is None:
        raise HTTPException(status_code=503, detail="Personalization engine not loaded")

    with tracer.start_as_current_span("borrower.match") as span:
        start_time = time.time()
        try:
            span.set_attribute("input.length", len(request.text))
            span.set_attribute("top_k", request.top_k)
            result = personalization.match(request.text, request.top_k)
            latency = time.time() - start_time

            MATCH_COUNT.labels(status="success").inc()
            MATCH_LATENCY.observe(latency)
            span.set_attribute("matches_returned", len(result["matches"]))
            span.set_status(Status(StatusCode.OK))

            return MatchResponse(
                matches=result["matches"],
                latency_ms=latency * 1000
            )
        except Exception as e:
            MATCH_COUNT.labels(status="error").inc()
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise HTTPException(status_code=500, detail=str(e))


# --- Edge Network Map ---
COMPUTE_LOCATION = GeoPoint(
    lat=float(os.getenv("COMPUTE_LAT", "41.8781")),
    lon=float(os.getenv("COMPUTE_LON", "-87.6298")),
    city=os.getenv("COMPUTE_CITY", "Chicago, IL"),
    region=os.getenv("COMPUTE_REGION", "us-ord"),
    label="LKE GPU Compute"
)


@app.get("/v1/network-info", response_model=NetworkInfoResponse)
async def network_info(request: Request):
    """Network topology info for the edge performance map."""
    true_client_ip = request.headers.get("true-client-ip")
    return NetworkInfoResponse(
        compute=COMPUTE_LOCATION,
        via_cdn=true_client_ip is not None,
        client_ip=true_client_ip or request.headers.get("x-real-ip"),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("SERVER_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVER_PORT", "8080")),
        workers=int(os.getenv("SERVER_WORKERS", "1"))
    )
