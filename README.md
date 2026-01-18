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
│   └── kustomization.yaml
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
