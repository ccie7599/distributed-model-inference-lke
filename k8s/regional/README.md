# Regional deployment

For `latency-sea` and `latency-fra2` clusters, which don't have cert-manager,
Vault Agent Injector, or Harbor containerd mirrors.

## One-time prerequisites (per cluster)

```bash
# 1. Label the GPU node (LKE doesn't auto-label new pool nodes)
kubectl label node <gpu-node> nvidia.com/gpu.present=true

# 2. Install nvidia-device-plugin with time-slicing (same manifest as primary)
kubectl apply -f ../nvidia-device-plugin.yaml

# 3. Create TLS secret (self-signed — Akamai edge terminates TLS with the real SAN cert)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /tmp/tls.key -out /tmp/tls.crt \
  -subj "/CN=mortgage-inference.connected-cloud.io"
kubectl -n demo-mortgage-inference create secret tls mortgage-inference-tls \
  --cert=/tmp/tls.crt --key=/tmp/tls.key

# 4. Copy demo-html ConfigMap from the primary cluster
kubectl --kubeconfig ~/.kube/presales-landing-zone.yaml -n demo-mortgage-inference \
  get configmap demo-html -o yaml | \
  kubectl apply -f -

# 5. Apply the deployment
kubectl apply -f deploy.yaml
```

## Rolling new image

```bash
kubectl -n demo-mortgage-inference set image deployment/mortgage-inference \
  mortgage-inference=brianapley/mortgage-inference:<new-sha>
```
