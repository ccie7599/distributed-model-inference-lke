# Observability

This project uses the [federated-k8s-observability](https://github.com/YOUR_ORG/federated-k8s-observability) framework for centralized observability across distributed clusters.

## Quick Setup

### Option 1: Remote Kustomize Reference

Reference the observability repo directly in your Kustomize configurations:

```yaml
# k8s/observability/hub/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - github.com/YOUR_ORG/federated-k8s-observability//base/hub?ref=v1.0.0
```

### Option 2: Git Submodule

```bash
git submodule add https://github.com/YOUR_ORG/federated-k8s-observability.git observability
```

## Deployment

### Deploy Hub (Central Cluster)

```bash
kubectl apply -k observability/hub/
```

### Deploy Edge Collector (This Cluster)

```bash
kubectl apply -k observability/edge/
```

## Configuration

See [observability/edge/kustomization.yaml](edge/kustomization.yaml) for cluster-specific settings:

- `CLUSTER_NAME`: Unique identifier for this cluster
- `CLUSTER_REGION`: Geographic region
- `HUB_ENDPOINT`: Central hub gateway address
