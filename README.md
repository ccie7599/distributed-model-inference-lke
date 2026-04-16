# Distributed BERT Inference on LKE

GPU-accelerated BERT inference deployed across three Linode Kubernetes Engine (LKE) clusters in the **Akamai Presales Landing Zone**, fronted by Akamai GTM for performance-based routing and CDN with query-string token auth.

**Live demo:** `https://mortgage-inference.connected-cloud.io/?token=<token>`

## Architecture

```
             [Browser]
                │
                ▼
         Akamai CDN (Enhanced TLS)
    prp_mortgage-inference.connected-cloud.io
                │
                ▼
        Akamai GTM (performance)
                │
     ┌──────────┼──────────┐
     ▼          ▼          ▼
  us-ord     us-sea      de-fra-2
  (Chicago)  (Seattle)   (Frankfurt 2)
  lke575271  lke589007   lke589020
     │          │          │
     ▼          ▼          ▼
  NodeBalancer per region (TCP passthrough :443)
     │          │          │
     ▼          ▼          ▼
  Inference Pod (per region)
  ├── bert-inference (ONNX Runtime + CUDA)
  └── tls-proxy (nginx — token auth, TLS, demo HTML)
```

## Components

- **Model**: `google-bert/bert-base-uncased`, exported to ONNX
- **Runtime**: ONNX Runtime with `CUDAExecutionProvider`
- **GPU**: 1× NVIDIA RTX 4000 Ada per region, time-sliced to advertise 4 replicas (demo workload, no VRAM contention)
- **TLS**: cert-manager + Let's Encrypt DNS-01 via Akamai Edge DNS (ClusterIssuer `letsencrypt-prod`)
- **Auth**: Query-string token with HttpOnly cookie persistence (nginx sidecar); `/health` and `/metrics` exempt
- **Edge cert**: Akamai CPS SAN enrollment 293468 (`sse.connected-cloud.io` shared SAN), Enhanced TLS
- **Observability**: OTel DaemonSet auto-scrape via `prometheus.io/*` annotations → Prometheus, Loki, Tempo, ClickHouse
- **DS2**: Full Akamai DataStream 2 fields to shared ingest at `ds2-im-demo.connected-cloud.io` → ClickHouse `ds2_raw` → Grafana CDN Analytics
- **GitOps**: ArgoCD Application in `lke575271` (primary). Regional clusters deployed via `kubectl apply -k k8s/` against each cluster's kubeconfig.

## Repo Layout

```
.
├── app/                    # Inference server (FastAPI + ONNX Runtime)
│   ├── Dockerfile          # nvidia/cuda:12.2.0 base, BERT model baked in
│   ├── inference_server.py
│   ├── requirements.txt
│   └── data/               # Mortgage product catalog + borrower profiles
├── demo/
│   └── index.html          # Browser demo UI with edge map, pre-warm, heartbeat
├── k8s/                    # ArgoCD-synced manifests (kustomize)
│   ├── namespace.yaml
│   ├── serviceaccount.yaml
│   ├── nginx-config.yaml   # tls-proxy sidecar config
│   ├── demo-html.yaml      # demo UI as ConfigMap
│   ├── deployment.yaml     # inference + tls-proxy sidecar
│   ├── service.yaml        # ClusterIP + LoadBalancer (NB)
│   ├── certificate.yaml    # cert-manager Certificate
│   ├── nvidia-device-plugin.yaml  # time-slicing config (apply separately)
│   └── kustomization.yaml
└── argocd/
    ├── application-ord.yaml   # Primary region
    └── README.md
```

## Deployment

Prerequisite setup is per-cluster (one-time):

1. Harbor imagePullSecret `harbor-creds` in `demo-mortgage-inference` namespace
2. cert-manager + `letsencrypt-prod` ClusterIssuer installed
3. nvidia-device-plugin with time-slicing config (apply `k8s/nvidia-device-plugin.yaml` once per cluster)

Then deploy:

```bash
# Primary (us-ord) — via ArgoCD
export KUBECONFIG=~/.kube/presales-landing-zone.yaml
kubectl apply -f argocd/application-ord.yaml

# Regional clusters — direct kubectl
kubectl --kubeconfig ~/.kube/latency-sea.yaml apply -k k8s/
kubectl --kubeconfig ~/.kube/latency-fra2.yaml apply -k k8s/
```

After the per-region NodeBalancer has an external IP, add it to the GTM property (`mortgage-inference.connectedcloud5.akadns.net`) and attach it to the firewall for Akamai OPIACL on 443.

## Endpoints

| Path | Auth | Purpose |
|---|---|---|
| `/` | token | Demo UI (HTML) |
| `/v1/classify` | token | POST — top-K mortgage product recommendations |
| `/v1/match` | token | POST — pattern match to borrower profiles |
| `/v1/models/bert` | token | GET — model metadata |
| `/v1/network-info` | token | GET — regional routing diagnostics |
| `/health` | none | Liveness + GTM liveness check |
| `/metrics` | none | Prometheus exposition |

## Known Behaviors

- **Time-slicing is cooperative, not isolated.** Four pods share one physical GPU — fine for demo workloads, not for production multi-tenancy. If latency spikes under concurrent load, reduce `replicas` in the nvidia-device-plugin config.
- **Firewall OPIACL ranges**: Akamai Enhanced TLS ghost servers live in `23.64.0.0/11`, `104.64.0.0/10`, `184.50.0.0/15`, `184.84.0.0/14` among others — ranges must include both Standard TLS and Enhanced TLS blocks or the edge can't reach origin.
- **GPU requires reset**: If CUDA can't detect the device after a pod thrash, reboot the node (`linode-cli linodes reboot <id>`).
- **LKE calico Typha**: Private network rules for clusters with Cloud Firewalls attached must allow TCP 5473 and 179 on `192.168.128.0/17` — without these, calico doesn't bootstrap after reboot.

## Links

- Landing Zone intake: `~/project-landing-zone/presales-landing-zone/docs/INTAKE.md`
- DS2 setup: `~/project-landing-zone/presales-landing-zone/docs/ds2-setup.md`
