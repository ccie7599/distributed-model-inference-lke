# ArgoCD Applications

This demo runs in three LZ clusters for distributed inference via Akamai GTM:

| Cluster | Region | GPU |
|---|---|---|
| lke575271 (presales-landing-zone) | us-ord (Chicago) | 1× RTX 4000 Ada, time-sliced x4 |
| lke589007 (latency-sea) | us-sea (Seattle) | 1× RTX 4000 Ada, time-sliced x4 |
| lke589020 (latency-fra2) | de-fra-2 (Frankfurt 2) | 1× RTX 4000 Ada, time-sliced x4 |

## Primary cluster (us-ord)

Apply `application-ord.yaml` to the ArgoCD running in the LZ primary cluster. It will sync `k8s/` from main branch.

```bash
export KUBECONFIG=~/.kube/presales-landing-zone.yaml
kubectl apply -f argocd/application-ord.yaml
```

## Regional clusters (us-sea, de-fra-2)

The regional `latency-*` clusters do not run their own ArgoCD. Apply `k8s/` directly via kustomize, scoped to the regional kubeconfig:

```bash
kubectl --kubeconfig ~/.kube/latency-sea.yaml apply -k k8s/
kubectl --kubeconfig ~/.kube/latency-fra2.yaml apply -k k8s/
```

Each region needs `mortgage-inference-tls` (cert-manager Certificate) and `harbor-creds` (imagePullSecret) set up first. See the per-cluster bootstrap notes in `docs/runbook.md`.
