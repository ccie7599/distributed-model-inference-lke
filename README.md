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
└── k8s/                # Kubernetes manifests
    ├── nvidia-device-plugin.yaml  # NVIDIA GPU device plugin
    ├── namespace.yaml  # Namespace definition
    ├── configmap.yaml  # Model and runtime configuration
    ├── pvc.yaml        # Persistent volume for model storage
    ├── deployment.yaml # BERT inference deployment
    ├── service.yaml    # Service definitions
    ├── hpa.yaml        # Horizontal Pod Autoscaler
    └── kustomization.yaml
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
