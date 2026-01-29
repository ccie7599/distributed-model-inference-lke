# Example Overlay

This directory contains example overlays demonstrating how to customize the federated observability stack for your environment.

## Directory Structure

```
example/
├── hub/                    # Central observability hub
│   └── kustomization.yaml
├── edge/                   # Edge cluster collectors
│   └── kustomization.yaml
└── README.md
```

## Usage

### 1. Copy and Customize

```bash
# Create your own overlay
cp -r overlays/example overlays/my-deployment

# Edit the configurations
vim overlays/my-deployment/hub/kustomization.yaml
vim overlays/my-deployment/edge/kustomization.yaml
```

### 2. Deploy Hub

```bash
# Deploy to your hub cluster
kubectl apply -k overlays/my-deployment/hub/

# Wait for pods
kubectl -n observability get pods -w

# Get external endpoints
kubectl -n observability get svc -l type=LoadBalancer
```

### 3. Deploy Edge Collectors

For each edge cluster:

```bash
# Create cluster-specific overlay
mkdir -p overlays/cluster-us-east-1/edge
cat > overlays/cluster-us-east-1/edge/kustomization.yaml << 'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../../base/edge
patches:
  - target:
      kind: ConfigMap
      name: edge-config
    patch: |-
      - op: replace
        path: /data/CLUSTER_NAME
        value: "cluster-us-east-1"
      - op: replace
        path: /data/CLUSTER_REGION
        value: "us-east"
      - op: replace
        path: /data/HUB_ENDPOINT
        value: "YOUR_HUB_IP:4317"
EOF

# Deploy
kubectl apply -k overlays/cluster-us-east-1/edge/
```

## Common Customizations

### Enable Datadog

```yaml
# hub/kustomization.yaml
components:
  - ../../../components/datadog
```

### Use Persistent Storage

```yaml
# hub/kustomization.yaml
patches:
  - target:
      kind: Deployment
      name: prometheus
    patch: |-
      - op: add
        path: /spec/template/spec/volumes/-
        value:
          name: prometheus-data
          persistentVolumeClaim:
            claimName: prometheus-pvc
```

### Add Custom Scrape Targets

Create a ConfigMap patch to add application-specific scrape configs to the OTel agent.

### Configure TLS

For production, enable TLS between edge and hub:

```yaml
# edge/kustomization.yaml
patches:
  - target:
      kind: ConfigMap
      name: edge-config
    patch: |-
      - op: replace
        path: /data/HUB_INSECURE
        value: "false"
```
