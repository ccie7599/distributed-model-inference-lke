#!/bin/bash
#
# Smoke test script for BERT inference service
# Performs quick connectivity and health checks
#
# Usage:
#   ./smoke_test.sh                          # Uses kubectl port-forward
#   ./smoke_test.sh http://<EXTERNAL-IP>     # Direct endpoint
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ENDPOINT="${1:-}"
PORT_FORWARD_PID=""
NAMESPACE="bert-inference"
SERVICE="bert-inference"
LOCAL_PORT="8080"

cleanup() {
    if [ -n "$PORT_FORWARD_PID" ]; then
        echo -e "\n${YELLOW}Cleaning up port-forward...${NC}"
        kill $PORT_FORWARD_PID 2>/dev/null || true
    fi
}

trap cleanup EXIT

print_header() {
    echo ""
    echo "=============================================="
    echo " BERT Inference Service - Smoke Test"
    echo "=============================================="
    echo ""
}

check_prerequisites() {
    echo "[*] Checking prerequisites..."

    if ! command -v curl &> /dev/null; then
        echo -e "${RED}[FAIL] curl is not installed${NC}"
        exit 1
    fi

    if ! command -v jq &> /dev/null; then
        echo -e "${YELLOW}[WARN] jq is not installed (optional, for JSON parsing)${NC}"
    fi

    echo -e "${GREEN}[OK] Prerequisites check passed${NC}"
}

setup_endpoint() {
    if [ -z "$ENDPOINT" ]; then
        echo "[*] No endpoint provided, setting up port-forward..."

        if ! command -v kubectl &> /dev/null; then
            echo -e "${RED}[FAIL] kubectl is not installed${NC}"
            exit 1
        fi

        # Check if service exists
        if ! kubectl -n $NAMESPACE get svc $SERVICE &> /dev/null; then
            echo -e "${RED}[FAIL] Service $SERVICE not found in namespace $NAMESPACE${NC}"
            exit 1
        fi

        # Start port-forward in background
        kubectl -n $NAMESPACE port-forward svc/$SERVICE $LOCAL_PORT:80 &> /dev/null &
        PORT_FORWARD_PID=$!

        # Wait for port-forward to be ready
        sleep 3

        if ! kill -0 $PORT_FORWARD_PID 2>/dev/null; then
            echo -e "${RED}[FAIL] Failed to establish port-forward${NC}"
            exit 1
        fi

        ENDPOINT="http://localhost:$LOCAL_PORT"
        echo -e "${GREEN}[OK] Port-forward established on $ENDPOINT${NC}"
    else
        echo "[*] Using provided endpoint: $ENDPOINT"
    fi
}

test_health() {
    echo ""
    echo "[Test 1] Health Check"
    echo "----------------------------------------"

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$ENDPOINT/health" 2>/dev/null || echo "000")

    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}[PASS] Health endpoint returned 200${NC}"
        return 0
    else
        echo -e "${RED}[FAIL] Health endpoint returned $HTTP_CODE${NC}"
        return 1
    fi
}

test_model_metadata() {
    echo ""
    echo "[Test 2] Model Metadata"
    echo "----------------------------------------"

    RESPONSE=$(curl -s --max-time 10 "$ENDPOINT/v1/models/bert" 2>/dev/null || echo "")

    if [ -n "$RESPONSE" ]; then
        echo -e "${GREEN}[PASS] Model metadata endpoint responded${NC}"
        if command -v jq &> /dev/null; then
            echo "$RESPONSE" | jq . 2>/dev/null || echo "$RESPONSE"
        else
            echo "$RESPONSE"
        fi
        return 0
    else
        echo -e "${RED}[FAIL] Model metadata endpoint did not respond${NC}"
        return 1
    fi
}

test_inference() {
    echo ""
    echo "[Test 3] Basic Inference"
    echo "----------------------------------------"

    # Simple inference payload (pre-tokenized for testing)
    # This is a minimal test - the actual tokenization would be done client-side
    PAYLOAD='{
        "inputs": {
            "input_ids": [[101, 2023, 2003, 1037, 3231, 102, 0, 0]],
            "attention_mask": [[1, 1, 1, 1, 1, 1, 0, 0]],
            "token_type_ids": [[0, 0, 0, 0, 0, 0, 0, 0]]
        }
    }'

    START_TIME=$(date +%s%N)
    HTTP_CODE=$(curl -s -o /tmp/inference_response.json -w "%{http_code}" \
        --max-time 30 \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD" \
        "$ENDPOINT/v1/models/bert:predict" 2>/dev/null || echo "000")
    END_TIME=$(date +%s%N)

    LATENCY_MS=$(( (END_TIME - START_TIME) / 1000000 ))

    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}[PASS] Inference request succeeded${NC}"
        echo "  Latency: ${LATENCY_MS}ms"
        if command -v jq &> /dev/null && [ -f /tmp/inference_response.json ]; then
            echo "  Response keys: $(jq -r 'keys | join(", ")' /tmp/inference_response.json 2>/dev/null || echo 'N/A')"
        fi
        return 0
    else
        echo -e "${RED}[FAIL] Inference request failed with HTTP $HTTP_CODE${NC}"
        if [ -f /tmp/inference_response.json ]; then
            cat /tmp/inference_response.json
        fi
        return 1
    fi
}

test_gpu_detection() {
    echo ""
    echo "[Test 4] GPU Detection (via kubectl)"
    echo "----------------------------------------"

    if ! command -v kubectl &> /dev/null; then
        echo -e "${YELLOW}[SKIP] kubectl not available${NC}"
        return 0
    fi

    GPU_COUNT=$(kubectl get nodes -o json 2>/dev/null | jq '[.items[].status.capacity["nvidia.com/gpu"] // "0" | tonumber] | add' 2>/dev/null || echo "0")

    if [ "$GPU_COUNT" != "0" ] && [ -n "$GPU_COUNT" ]; then
        echo -e "${GREEN}[PASS] Detected $GPU_COUNT GPU(s) in cluster${NC}"
        return 0
    else
        echo -e "${YELLOW}[WARN] No GPUs detected in cluster (may still work with CPU)${NC}"
        return 0
    fi
}

test_pod_status() {
    echo ""
    echo "[Test 5] Pod Status"
    echo "----------------------------------------"

    if ! command -v kubectl &> /dev/null; then
        echo -e "${YELLOW}[SKIP] kubectl not available${NC}"
        return 0
    fi

    RUNNING_PODS=$(kubectl -n $NAMESPACE get pods -l app=bert-inference --field-selector=status.phase=Running -o name 2>/dev/null | wc -l)
    TOTAL_PODS=$(kubectl -n $NAMESPACE get pods -l app=bert-inference -o name 2>/dev/null | wc -l)

    if [ "$RUNNING_PODS" -gt 0 ]; then
        echo -e "${GREEN}[PASS] $RUNNING_PODS/$TOTAL_PODS pods running${NC}"
        kubectl -n $NAMESPACE get pods -l app=bert-inference 2>/dev/null
        return 0
    else
        echo -e "${RED}[FAIL] No running pods found${NC}"
        kubectl -n $NAMESPACE get pods -l app=bert-inference 2>/dev/null
        return 1
    fi
}

print_summary() {
    echo ""
    echo "=============================================="
    echo " Summary"
    echo "=============================================="
    echo ""
    echo "  Health Check:     $HEALTH_RESULT"
    echo "  Model Metadata:   $METADATA_RESULT"
    echo "  Basic Inference:  $INFERENCE_RESULT"
    echo "  GPU Detection:    $GPU_RESULT"
    echo "  Pod Status:       $POD_RESULT"
    echo ""
    echo "=============================================="
}

# Main execution
print_header
check_prerequisites
setup_endpoint

HEALTH_RESULT="${RED}FAIL${NC}"
METADATA_RESULT="${RED}FAIL${NC}"
INFERENCE_RESULT="${RED}FAIL${NC}"
GPU_RESULT="${YELLOW}SKIP${NC}"
POD_RESULT="${YELLOW}SKIP${NC}"

test_health && HEALTH_RESULT="${GREEN}PASS${NC}"
test_model_metadata && METADATA_RESULT="${GREEN}PASS${NC}"
test_inference && INFERENCE_RESULT="${GREEN}PASS${NC}"
test_gpu_detection && GPU_RESULT="${GREEN}PASS${NC}"
test_pod_status && POD_RESULT="${GREEN}PASS${NC}"

print_summary

# Cleanup temp files
rm -f /tmp/inference_response.json

echo "Smoke test completed."
