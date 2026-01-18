# Distributed BERT Model Inference on LKE

This project deploys a BERT model inference service using ONNX Runtime on Linode Kubernetes Engine (LKE) with GPU support.

## Architecture

- **Model**: google-bert/bert-base-uncased
- **Runtime**: ONNX Runtime with CUDA execution provider
- **Infrastructure**: Linode Kubernetes Engine with GPU node pools

## Prerequisites

- [Terraform](https://www.terraform.io/downloads) >= 1.0.0
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [Linode API Token](https://cloud.linode.com/profile/tokens)

## Project Structure

```
.
├── terraform/           # Infrastructure as Code for LKE cluster
│   ├── main.tf         # LKE cluster configuration
│   ├── variables.tf    # Input variables
│   ├── outputs.tf      # Output values
│   └── providers.tf    # Provider configuration
│
├── k8s/                # Kubernetes manifests
│   ├── nvidia-device-plugin.yaml  # NVIDIA GPU device plugin
│   ├── namespace.yaml  # Namespace definition
│   ├── configmap.yaml  # Model and runtime configuration
│   ├── pvc.yaml        # Persistent volume for model storage
│   ├── deployment.yaml # BERT inference deployment
│   ├── service.yaml    # Service definitions
│   ├── hpa.yaml        # Horizontal Pod Autoscaler
│   ├── kustomization.yaml
│   ├── monitoring/     # Observability stack
│   │   ├── prometheus-*.yaml   # Prometheus deployment
│   │   ├── grafana-*.yaml      # Grafana with dashboards
│   │   └── dcgm-exporter.yaml  # NVIDIA GPU metrics
│   └── ingress/        # TLS/Ingress configuration
│       ├── nginx-ingress.yaml    # NGINX Ingress Controller
│       ├── cluster-issuers.yaml  # Let's Encrypt issuers
│       ├── ingress-tls.yaml      # Ingress with TLS
│       └── configure-domains.sh  # Domain setup helper
│
├── app/                # Inference server with metrics
│   ├── inference_server.py  # FastAPI server with Prometheus instrumentation
│   ├── Dockerfile
│   └── requirements.txt
│
└── tests/              # Test scripts
    ├── smoke_test.sh   # Quick connectivity and health checks
    ├── test_inference.py   # Functional inference tests
    ├── load_test.py    # Load/stress testing
    └── requirements.txt
```

## Deployment

### 1. Provision LKE Cluster

```bash
cd terraform

# Copy and configure variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your Linode API token

# Initialize and apply
terraform init
terraform plan
terraform apply
```

### 2. Configure kubectl

```bash
export KUBECONFIG=$(pwd)/kubeconfig.yaml
kubectl get nodes
```

### 3. Install NVIDIA Device Plugin

The NVIDIA device plugin is required to expose GPU resources to Kubernetes:

```bash
cd ../k8s

# Deploy NVIDIA device plugin
kubectl apply -f nvidia-device-plugin.yaml

# Verify plugin is running on GPU nodes
kubectl -n kube-system get pods -l app=nvidia-device-plugin

# Confirm GPUs are detected (should show nvidia.com/gpu capacity)
kubectl get nodes -o json | jq '.items[].status.capacity'
```

### 4. Deploy BERT Inference Service

```bash
# Deploy all resources
kubectl apply -k .

# Verify deployment
kubectl -n bert-inference get pods
kubectl -n bert-inference get svc
```

### 5. Access the Service

```bash
# Get external IP
kubectl -n bert-inference get svc bert-inference-external

# Test inference endpoint
curl http://<EXTERNAL-IP>/v1/models/bert
```

## Configuration

### Terraform Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `linode_token` | Linode API token | (required) |
| `cluster_label` | Cluster name | `bert-inference-cluster` |
| `region` | Linode region | `us-ord` |
| `gpu_node_type` | GPU instance type | `g1-gpu-rtx6000-1` |
| `gpu_node_count` | Number of GPU nodes | `1` |

### Model Configuration

Edit `k8s/configmap.yaml` to adjust:
- `MAX_SEQUENCE_LENGTH`: Maximum input sequence length
- `BATCH_SIZE`: Inference batch size
- `ONNX_EXECUTION_PROVIDER`: Execution provider (CUDA/CPU)

## Scaling

The HPA automatically scales pods based on CPU/memory utilization. To manually scale:

```bash
kubectl -n bert-inference scale deployment bert-inference --replicas=2
```

## Observability

The project includes a complete observability stack with Prometheus, Grafana, and NVIDIA DCGM Exporter.

### Deploy Monitoring Stack

```bash
# Deploy Prometheus, Grafana, and DCGM Exporter
kubectl apply -k k8s/monitoring/

# Verify deployments
kubectl -n monitoring get pods

# Get Grafana external IP
kubectl -n monitoring get svc grafana-external
```

### Access Grafana

1. Open `http://<GRAFANA-EXTERNAL-IP>` in your browser
2. Login with:
   - Username: `admin`
   - Password: `BertInference2024!`
3. Navigate to **Dashboards > BERT Inference > BERT Inference Dashboard**

### Available Metrics

#### Inference Metrics
| Metric | Description |
|--------|-------------|
| `inference_requests_total` | Total requests by status (success/error) |
| `inference_request_duration_seconds` | Request latency histogram |
| `inference_tokens_processed_total` | Total tokens processed |
| `inference_batch_size` | Batch size distribution |
| `inference_active_requests` | Currently processing requests |

#### GPU Metrics (via DCGM)
| Metric | Description |
|--------|-------------|
| `DCGM_FI_DEV_GPU_UTIL` | GPU utilization percentage |
| `DCGM_FI_DEV_FB_USED` | GPU memory used (MB) |
| `DCGM_FI_DEV_FB_FREE` | GPU memory free (MB) |
| `DCGM_FI_DEV_GPU_TEMP` | GPU temperature (°C) |
| `DCGM_FI_DEV_POWER_USAGE` | GPU power consumption (W) |

### Dashboard Panels

The pre-configured Grafana dashboard includes:

```
┌─────────────────────────────────────────────────────────────────┐
│  BERT Inference Dashboard                                        │
├─────────────────┬─────────────────┬─────────────────────────────┤
│ Avg Latency     │ P95 Latency     │ Requests/sec │ Error Rate   │
├─────────────────┴─────────────────┴─────────────────────────────┤
│ Request Latency Distribution    │ Request Throughput            │
├─────────────────────────────────┴───────────────────────────────┤
│ GPU Utilization │ GPU Memory │ GPU Temp │ GPU Power             │
├─────────────────┴────────────┴──────────┴───────────────────────┤
│ Pod CPU Usage               │ Pod Memory Usage                  │
├─────────────────────────────┴───────────────────────────────────┤
│ HPA Replica Count           │ Pod Restarts                      │
└─────────────────────────────────────────────────────────────────┘
```

### Port-Forward Access

For local access without LoadBalancer:

```bash
# Prometheus
kubectl -n monitoring port-forward svc/prometheus 9090:9090

# Grafana
kubectl -n monitoring port-forward svc/grafana 3000:3000
```

### Custom Metrics Instrumentation

The `app/inference_server.py` demonstrates how to instrument a FastAPI inference server with Prometheus metrics:

```python
from prometheus_client import Counter, Histogram, Gauge

REQUEST_LATENCY = Histogram(
    "inference_request_duration_seconds",
    "Inference request latency",
    ["model"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# In your inference function:
with REQUEST_LATENCY.labels(model="bert").time():
    result = model.predict(inputs)
```

## TLS with Let's Encrypt

The project includes NGINX Ingress Controller and cert-manager integration for automatic TLS certificate provisioning via Let's Encrypt.

### Quick Setup

```bash
# 1. Configure your domain (replaces example.com with your domain)
cd k8s/ingress
./configure-domains.sh yourdomain.com your-email@yourdomain.com

# 2. Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml

# 3. Wait for cert-manager to be ready
kubectl -n cert-manager wait --for=condition=ready pod -l app.kubernetes.io/instance=cert-manager --timeout=300s

# 4. Deploy ingress resources
kubectl apply -k k8s/ingress/

# 5. Get LoadBalancer IP
kubectl -n ingress-nginx get svc ingress-nginx-controller
```

### DNS Configuration

Point your DNS A records to the Ingress LoadBalancer IP:

| Subdomain | Service |
|-----------|---------|
| `inference.yourdomain.com` | BERT Inference API |
| `grafana.yourdomain.com` | Grafana Dashboard |
| `prometheus.yourdomain.com` | Prometheus Metrics |

### Verify Certificates

```bash
# Check certificate status
kubectl get certificates -A

# View certificate details
kubectl -n bert-inference describe certificate bert-inference-tls

# Test HTTPS endpoints
curl https://inference.yourdomain.com/health
curl https://grafana.yourdomain.com/api/health
```

### Architecture

```
                    ┌─────────────────────┐
                    │   Let's Encrypt     │
                    │   ACME Server       │
                    └──────────┬──────────┘
                               │ Certificate
                               ▼ Issuance
┌──────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                     │
│  ┌─────────────────┐    ┌─────────────────────────────┐  │
│  │  cert-manager   │───▶│  TLS Secrets                │  │
│  └─────────────────┘    │  (auto-renewed)             │  │
│                         └──────────────┬──────────────┘  │
│                                        │                 │
│  ┌─────────────────────────────────────▼──────────────┐  │
│  │           NGINX Ingress Controller                 │  │
│  │           (LoadBalancer :443)                      │  │
│  └──────┬─────────────┬────────────────┬──────────────┘  │
│         │             │                │                 │
│         ▼             ▼                ▼                 │
│  ┌────────────┐ ┌──────────┐ ┌─────────────────────┐    │
│  │ Inference  │ │ Grafana  │ │     Prometheus      │    │
│  │  Service   │ │ :3000    │ │       :9090         │    │
│  └────────────┘ └──────────┘ └─────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

### Ingress Annotations

The ingress resources include useful annotations:

```yaml
annotations:
  cert-manager.io/cluster-issuer: letsencrypt-prod  # Auto TLS
  nginx.ingress.kubernetes.io/ssl-redirect: "true"  # Force HTTPS
  nginx.ingress.kubernetes.io/proxy-body-size: "50m"  # Large payloads
  nginx.ingress.kubernetes.io/proxy-read-timeout: "300"  # Long inference
```

### Staging vs Production

For testing, use the staging issuer (avoids rate limits):

```bash
# Edit ingress-tls.yaml
sed -i 's/letsencrypt-prod/letsencrypt-staging/g' k8s/ingress/ingress-tls.yaml
kubectl apply -f k8s/ingress/ingress-tls.yaml
```

**Note:** Staging certificates are not trusted by browsers but are useful for testing the setup.

## Testing

### Prerequisites

```bash
cd tests
pip install -r requirements.txt
```

### Smoke Test

Quick connectivity and health check (no Python dependencies required):

```bash
# Using kubectl port-forward (automatic)
./smoke_test.sh

# Or with direct endpoint
./smoke_test.sh http://<EXTERNAL-IP>
```

**Test Scenarios:**
1. Health endpoint check
2. Model metadata retrieval
3. Basic inference request
4. GPU detection verification
5. Pod status validation

### Functional Tests

Comprehensive inference testing with the Python test suite:

```bash
# Run all test scenarios
python test_inference.py --endpoint http://<EXTERNAL-IP>

# Save results to JSON
python test_inference.py --endpoint http://<EXTERNAL-IP> --output results.json
```

**Test Scenarios:**
1. **Health Check** - Verifies service is responding
2. **Single Inference** - Tests individual text inference
3. **Batch Inference** - Tests batched requests (4 samples)
4. **Latency Test** - Measures latency over 10 sequential requests

### Load Testing

Stress test the service with concurrent requests:

```bash
# Default: 100 requests, 10 concurrent
python load_test.py --endpoint http://<EXTERNAL-IP>

# Custom load parameters
python load_test.py \
  --endpoint http://<EXTERNAL-IP> \
  --requests 500 \
  --concurrency 20 \
  --output load_results.json
```

**Metrics Collected:**
- Throughput (requests/second)
- Latency percentiles (p50, p90, p95, p99)
- Success/failure rates
- Error categorization

### Example Test Run

```bash
# 1. Deploy the service
kubectl apply -k k8s/

# 2. Wait for pods to be ready
kubectl -n bert-inference wait --for=condition=ready pod -l app=bert-inference --timeout=300s

# 3. Run smoke test
cd tests
./smoke_test.sh

# 4. Run functional tests
python test_inference.py --endpoint http://localhost:8080

# 5. Run load test
python load_test.py --endpoint http://localhost:8080 --requests 50 --concurrency 5
```

## Cleanup

```bash
# Delete Kubernetes resources
kubectl delete -k k8s/

# Destroy infrastructure
cd terraform
terraform destroy
```

## License

MIT
