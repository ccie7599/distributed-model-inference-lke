# Federated Kubernetes Observability

A reusable, modular observability framework for distributed Kubernetes clusters. This framework implements a federated pattern where edge clusters collect and forward telemetry to a central hub for aggregation, visualization, and optional forwarding to third-party platforms.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              EDGE CLUSTERS                                       │
│                                                                                  │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                      │
│   │  Cluster A   │    │  Cluster B   │    │  Cluster N   │                      │
│   │              │    │              │    │              │                      │
│   │ ┌──────────┐ │    │ ┌──────────┐ │    │ ┌──────────┐ │                      │
│   │ │ Workloads│ │    │ │ Workloads│ │    │ │ Workloads│ │                      │
│   │ └────┬─────┘ │    │ └────┬─────┘ │    │ └────┬─────┘ │                      │
│   │      │       │    │      │       │    │      │       │                      │
│   │ ┌────▼─────┐ │    │ ┌────▼─────┐ │    │ ┌────▼─────┐ │                      │
│   │ │OTel Agent│ │    │ │OTel Agent│ │    │ │OTel Agent│ │  ← Metrics/Logs/     │
│   │ │Fluent Bit│ │    │ │Fluent Bit│ │    │ │Fluent Bit│ │    Traces Collection │
│   │ └────┬─────┘ │    │ └────┬─────┘ │    │ └────┬─────┘ │                      │
│   └──────┼───────┘    └──────┼───────┘    └──────┼───────┘                      │
│          │                   │                   │                              │
└──────────┼───────────────────┼───────────────────┼──────────────────────────────┘
           │                   │                   │
           └───────────────────┼───────────────────┘
                               │ OTLP (gRPC/HTTP)
                               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           CENTRAL HUB                                            │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                     OpenTelemetry Gateway                                   │ │
│  │  ┌─────────┐  ┌───────────┐  ┌──────────────────────────────────────────┐  │ │
│  │  │Receivers│→ │Processors │→ │              Exporters                    │  │ │
│  │  │ OTLP    │  │ batch     │  │ prometheusremotewrite → Prometheus       │  │ │
│  │  │         │  │ k8sattr   │  │ loki                  → Loki             │  │ │
│  │  │         │  │ memory    │  │ otlp                  → Tempo            │  │ │
│  │  │         │  │ filter    │  │ datadog               → Datadog (opt)    │  │ │
│  │  └─────────┘  └───────────┘  └──────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐                │
│  │ Prometheus │  │    Loki    │  │   Tempo    │  │  Grafana   │                │
│  │  (Metrics) │  │   (Logs)   │  │  (Traces)  │  │ (Visualize)│                │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘                │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Features

- **Unified Telemetry**: Metrics, logs, and traces from all clusters in one place
- **Cluster Identification**: Automatic labeling with cluster name, region, environment
- **Kubernetes-Native**: Auto-discovery of pods, services, and nodes
- **Scalable**: Designed for multi-cluster deployments
- **Extensible**: Kustomize-based for easy customization
- **Third-Party Integration**: Optional Datadog forwarding included

## Directory Structure

```
observability/
├── base/                        # Application-agnostic base configs
│   ├── edge/                    # Deploy on each edge cluster
│   │   ├── otel-agent/          # OpenTelemetry Collector (agent mode)
│   │   └── fluent-bit/          # Log collection
│   └── hub/                     # Deploy on central cluster
│       ├── otel-gateway/        # OpenTelemetry Collector (gateway mode)
│       ├── prometheus/          # Metrics storage
│       ├── loki/                # Log storage
│       ├── tempo/               # Trace storage
│       └── grafana/             # Visualization
├── components/                  # Optional add-on components
│   └── datadog/                 # Datadog integration
└── overlays/                    # Environment-specific configurations
    └── example/                 # Example overlay
```

## Quick Start

### 1. Deploy Central Hub

```bash
# Create overlay for your hub cluster
mkdir -p overlays/my-hub/hub
cat > overlays/my-hub/hub/kustomization.yaml << 'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../../base/hub
EOF

# Deploy
kubectl apply -k overlays/my-hub/hub/
```

### 2. Get Hub Endpoint

```bash
# Wait for external IP
kubectl -n observability get svc otel-gateway-lb -w
```

### 3. Deploy Edge Collectors

```bash
# Create overlay for each edge cluster
mkdir -p overlays/my-edge-cluster/edge

cat > overlays/my-edge-cluster/edge/kustomization.yaml << 'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../../base/edge
patches:
  - patch: |-
      - op: replace
        path: /data/CLUSTER_NAME
        value: "my-cluster-name"
      - op: replace
        path: /data/CLUSTER_REGION
        value: "us-east"
      - op: replace
        path: /data/HUB_ENDPOINT
        value: "your-hub-ip:4317"
    target:
      kind: ConfigMap
      name: edge-config
EOF

# Deploy to edge cluster
kubectl apply -k overlays/my-edge-cluster/edge/
```

### 4. Enable Datadog (Optional)

```bash
# Create Datadog secret
kubectl -n observability create secret generic datadog-credentials \
  --from-literal=api-key=YOUR_API_KEY

# Include Datadog component in your hub overlay
cat > overlays/my-hub/hub/kustomization.yaml << 'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../../base/hub
components:
  - ../../../components/datadog
EOF
```

## Configuration

### Edge Cluster Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `CLUSTER_NAME` | Unique identifier for the cluster | `edge-cluster` |
| `CLUSTER_REGION` | Geographic region | `unknown` |
| `CLUSTER_ENVIRONMENT` | Environment (prod/staging/dev) | `production` |
| `HUB_ENDPOINT` | Central hub OTel gateway address | `otel-gateway:4317` |
| `HUB_INSECURE` | Use insecure connection | `true` |

### Hub Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `PROMETHEUS_RETENTION` | Metrics retention period | `15d` |
| `LOKI_RETENTION` | Log retention period | `168h` (7d) |
| `TEMPO_RETENTION` | Trace retention period | `72h` (3d) |

### Datadog Settings

| Variable | Description | Required |
|----------|-------------|----------|
| `DD_API_KEY` | Datadog API key | Yes |
| `DD_SITE` | Datadog site (datadoghq.com, datadoghq.eu) | No |

## Instrumenting Applications

### Metrics

Applications can expose Prometheus metrics. Add annotations to enable scraping:

```yaml
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8080"
    prometheus.io/path: "/metrics"
```

### Logs

Logs are automatically collected from stdout/stderr. For structured logging, output JSON:

```json
{"level": "info", "message": "Request processed", "request_id": "abc123", "duration_ms": 42}
```

### Traces

Send traces via OTLP to the local agent:

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-agent.observability:4317
```

## Grafana Dashboards

Pre-configured dashboards:

1. **Cluster Overview** - Multi-cluster health summary
2. **Resource Usage** - CPU, memory, network by cluster
3. **Log Explorer** - Centralized log search
4. **Trace Explorer** - Distributed tracing view

Access Grafana:
```bash
kubectl -n observability port-forward svc/grafana 3000:3000
# Open http://localhost:3000 (admin/admin)
```

## Scaling Considerations

### Small (< 5 clusters)
- Default configuration works well
- Single replica for hub components

### Medium (5-20 clusters)
- Increase hub component resources
- Consider Prometheus remote write to long-term storage

### Large (20+ clusters)
- Deploy hub components with HA (multiple replicas)
- Use Mimir/Cortex instead of single Prometheus
- Consider sharding logs by cluster

## Troubleshooting

### Verify Edge Collector

```bash
# Check agent status
kubectl -n observability logs -l app=otel-agent --tail=50

# Check if metrics are being collected
kubectl -n observability port-forward svc/otel-agent 8888:8888
curl http://localhost:8888/metrics
```

### Verify Hub Connectivity

```bash
# From edge cluster, test connectivity
kubectl -n observability exec -it deploy/otel-agent -- \
  wget -qO- http://HUB_ENDPOINT:4317/health
```

### Check Datadog Export

```bash
# View Datadog exporter logs
kubectl -n observability logs -l app=otel-gateway | grep -i datadog
```
