# Datadog Integration Component

This Kustomize component adds Datadog export capability to the federated observability hub.

## Usage

Include this component in your hub overlay:

```yaml
# overlays/my-hub/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base/hub
components:
  - ../../components/datadog
```

## Configuration

### Option 1: Create Secret Separately (Recommended)

Before deploying, create the Datadog credentials secret:

```bash
kubectl -n observability create secret generic datadog-credentials \
  --from-literal=api-key=YOUR_DATADOG_API_KEY \
  --from-literal=site=datadoghq.com
```

Then patch the component to not create the secret:

```yaml
# overlays/my-hub/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base/hub
components:
  - ../../components/datadog
patchesStrategicMerge:
  - delete-secret.yaml
```

```yaml
# overlays/my-hub/delete-secret.yaml
$patch: delete
apiVersion: v1
kind: Secret
metadata:
  name: datadog-credentials
  namespace: observability
```

### Option 2: Patch Secret Values

Override the secret values in your overlay:

```yaml
# overlays/my-hub/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base/hub
components:
  - ../../components/datadog
secretGenerator:
  - name: datadog-credentials
    namespace: observability
    behavior: replace
    literals:
      - api-key=your-actual-api-key
      - site=datadoghq.com
```

## Datadog Sites

| Site | Domain |
|------|--------|
| US1 (default) | datadoghq.com |
| US3 | us3.datadoghq.com |
| US5 | us5.datadoghq.com |
| EU | datadoghq.eu |
| AP1 | ap1.datadoghq.com |

## What Gets Exported

- **Metrics**: All metrics collected from edge clusters
- **Logs**: All logs collected via Fluent Bit
- **Traces**: All traces received via OTLP

### Resource Attributes as Tags

The following resource attributes are automatically converted to Datadog tags:

- `k8s.cluster.name` → `cluster`
- `k8s.cluster.region` → `region`
- `deployment.environment` → `env`
- `k8s.namespace.name` → `kube_namespace`
- `k8s.pod.name` → `pod_name`
- `k8s.deployment.name` → `kube_deployment`
