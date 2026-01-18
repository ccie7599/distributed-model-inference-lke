#!/bin/bash
#
# Configure TLS domains for BERT inference services
#
# Usage:
#   ./configure-domains.sh <base-domain> [email]
#
# Example:
#   ./configure-domains.sh mycompany.com admin@mycompany.com
#
# This will configure:
#   - inference.mycompany.com -> BERT Inference Service
#   - grafana.mycompany.com   -> Grafana Dashboard
#   - prometheus.mycompany.com -> Prometheus Metrics
#

set -e

BASE_DOMAIN="${1:-}"
EMAIL="${2:-admin@example.com}"

if [ -z "$BASE_DOMAIN" ]; then
    echo "Usage: $0 <base-domain> [email]"
    echo ""
    echo "Example: $0 mycompany.com admin@mycompany.com"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Configuring TLS for domain: $BASE_DOMAIN"
echo "Let's Encrypt email: $EMAIL"
echo ""

# Update ClusterIssuers with email
echo "[1/3] Updating ClusterIssuers with email..."
sed -i "s/email: admin@example.com/email: $EMAIL/g" "$SCRIPT_DIR/cluster-issuers.yaml"

# Update Ingress resources with domains
echo "[2/3] Updating Ingress resources with domains..."
sed -i "s/inference.example.com/inference.$BASE_DOMAIN/g" "$SCRIPT_DIR/ingress-tls.yaml"
sed -i "s/grafana.example.com/grafana.$BASE_DOMAIN/g" "$SCRIPT_DIR/ingress-tls.yaml"
sed -i "s/prometheus.example.com/prometheus.$BASE_DOMAIN/g" "$SCRIPT_DIR/ingress-tls.yaml"

echo "[3/3] Configuration complete!"
echo ""
echo "Next steps:"
echo ""
echo "1. Install cert-manager:"
echo "   kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml"
echo ""
echo "2. Wait for cert-manager to be ready:"
echo "   kubectl -n cert-manager wait --for=condition=ready pod -l app.kubernetes.io/instance=cert-manager --timeout=300s"
echo ""
echo "3. Apply ingress resources:"
echo "   kubectl apply -k $SCRIPT_DIR"
echo ""
echo "4. Get the Ingress LoadBalancer IP:"
echo "   kubectl -n ingress-nginx get svc ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}'"
echo ""
echo "5. Configure DNS records (A records pointing to the LoadBalancer IP):"
echo "   inference.$BASE_DOMAIN -> <LOADBALANCER_IP>"
echo "   grafana.$BASE_DOMAIN   -> <LOADBALANCER_IP>"
echo "   prometheus.$BASE_DOMAIN -> <LOADBALANCER_IP>"
echo ""
echo "6. Wait for certificates to be issued (may take a few minutes):"
echo "   kubectl get certificates -A"
echo ""
echo "7. Access your services:"
echo "   https://inference.$BASE_DOMAIN"
echo "   https://grafana.$BASE_DOMAIN"
echo "   https://prometheus.$BASE_DOMAIN"
