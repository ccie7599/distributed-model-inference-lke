#!/usr/bin/env python3
"""
Test script for BERT ONNX inference service.

Usage:
    python test_inference.py --endpoint http://localhost:8080
    python test_inference.py --endpoint http://<EXTERNAL-IP>
"""

import argparse
import json
import sys
import time
from typing import Optional

import numpy as np
import requests
from transformers import BertTokenizer


class BertInferenceClient:
    """Client for testing BERT ONNX inference service."""

    def __init__(self, endpoint: str, timeout: int = 30):
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.tokenizer = BertTokenizer.from_pretrained("google-bert/bert-base-uncased")

    def health_check(self) -> bool:
        """Check if the inference service is healthy."""
        try:
            response = requests.get(
                f"{self.endpoint}/health",
                timeout=self.timeout
            )
            return response.status_code == 200
        except requests.RequestException as e:
            print(f"Health check failed: {e}")
            return False

    def tokenize(self, text: str, max_length: int = 128) -> dict:
        """Tokenize input text for BERT model."""
        encoded = self.tokenizer(
            text,
            padding="max_length",
            truncation=True,
            max_length=max_length,
            return_tensors="np"
        )
        return {
            "input_ids": encoded["input_ids"].tolist(),
            "attention_mask": encoded["attention_mask"].tolist(),
            "token_type_ids": encoded["token_type_ids"].tolist()
        }

    def infer(self, text: str, max_length: int = 128) -> Optional[dict]:
        """Send inference request to the service."""
        inputs = self.tokenize(text, max_length)

        payload = {
            "inputs": inputs
        }

        try:
            start_time = time.time()
            response = requests.post(
                f"{self.endpoint}/v1/models/bert:predict",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout
            )
            latency = (time.time() - start_time) * 1000

            if response.status_code == 200:
                result = response.json()
                result["latency_ms"] = latency
                return result
            else:
                print(f"Inference failed: {response.status_code} - {response.text}")
                return None

        except requests.RequestException as e:
            print(f"Inference request failed: {e}")
            return None

    def batch_infer(self, texts: list[str], max_length: int = 128) -> Optional[dict]:
        """Send batch inference request."""
        batch_inputs = {
            "input_ids": [],
            "attention_mask": [],
            "token_type_ids": []
        }

        for text in texts:
            inputs = self.tokenize(text, max_length)
            batch_inputs["input_ids"].extend(inputs["input_ids"])
            batch_inputs["attention_mask"].extend(inputs["attention_mask"])
            batch_inputs["token_type_ids"].extend(inputs["token_type_ids"])

        payload = {"inputs": batch_inputs}

        try:
            start_time = time.time()
            response = requests.post(
                f"{self.endpoint}/v1/models/bert:predict",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout
            )
            latency = (time.time() - start_time) * 1000

            if response.status_code == 200:
                result = response.json()
                result["latency_ms"] = latency
                result["batch_size"] = len(texts)
                return result
            else:
                print(f"Batch inference failed: {response.status_code}")
                return None

        except requests.RequestException as e:
            print(f"Batch inference request failed: {e}")
            return None


def run_test_scenarios(client: BertInferenceClient) -> dict:
    """Run all test scenarios and return results."""
    results = {
        "health_check": False,
        "single_inference": False,
        "batch_inference": False,
        "latency_test": False,
        "details": {}
    }

    print("\n" + "=" * 60)
    print("BERT Inference Service Test Suite")
    print("=" * 60)

    # Test 1: Health Check
    print("\n[Test 1] Health Check...")
    results["health_check"] = client.health_check()
    status = "PASS" if results["health_check"] else "FAIL"
    print(f"  Status: {status}")

    if not results["health_check"]:
        print("  Service is not healthy. Aborting remaining tests.")
        return results

    # Test 2: Single Inference
    print("\n[Test 2] Single Inference...")
    test_text = "The quick brown fox jumps over the lazy dog."
    result = client.infer(test_text)
    if result:
        results["single_inference"] = True
        results["details"]["single_inference"] = {
            "input": test_text,
            "latency_ms": result.get("latency_ms", 0)
        }
        print(f"  Status: PASS")
        print(f"  Input: '{test_text}'")
        print(f"  Latency: {result.get('latency_ms', 0):.2f}ms")
    else:
        print(f"  Status: FAIL")

    # Test 3: Batch Inference
    print("\n[Test 3] Batch Inference...")
    test_texts = [
        "Machine learning is transforming industries.",
        "Natural language processing enables computers to understand text.",
        "BERT is a powerful language model developed by Google.",
        "Kubernetes orchestrates containerized applications."
    ]
    result = client.batch_infer(test_texts)
    if result:
        results["batch_inference"] = True
        results["details"]["batch_inference"] = {
            "batch_size": len(test_texts),
            "latency_ms": result.get("latency_ms", 0),
            "per_sample_latency_ms": result.get("latency_ms", 0) / len(test_texts)
        }
        print(f"  Status: PASS")
        print(f"  Batch size: {len(test_texts)}")
        print(f"  Total latency: {result.get('latency_ms', 0):.2f}ms")
        print(f"  Per-sample latency: {result.get('latency_ms', 0) / len(test_texts):.2f}ms")
    else:
        print(f"  Status: FAIL")

    # Test 4: Latency Test (10 sequential requests)
    print("\n[Test 4] Latency Test (10 sequential requests)...")
    latencies = []
    test_text = "Testing inference latency with a sample sentence."
    for i in range(10):
        result = client.infer(test_text)
        if result:
            latencies.append(result.get("latency_ms", 0))
        else:
            break

    if len(latencies) == 10:
        results["latency_test"] = True
        results["details"]["latency_test"] = {
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "avg_ms": sum(latencies) / len(latencies),
            "p50_ms": sorted(latencies)[5],
            "p95_ms": sorted(latencies)[9]
        }
        print(f"  Status: PASS")
        print(f"  Min: {min(latencies):.2f}ms")
        print(f"  Max: {max(latencies):.2f}ms")
        print(f"  Avg: {sum(latencies) / len(latencies):.2f}ms")
        print(f"  P50: {sorted(latencies)[5]:.2f}ms")
        print(f"  P95: {sorted(latencies)[9]:.2f}ms")
    else:
        print(f"  Status: FAIL (only {len(latencies)}/10 requests succeeded)")

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum([
        results["health_check"],
        results["single_inference"],
        results["batch_inference"],
        results["latency_test"]
    ])
    print(f"  Passed: {passed}/4")
    print(f"  Health Check:     {'PASS' if results['health_check'] else 'FAIL'}")
    print(f"  Single Inference: {'PASS' if results['single_inference'] else 'FAIL'}")
    print(f"  Batch Inference:  {'PASS' if results['batch_inference'] else 'FAIL'}")
    print(f"  Latency Test:     {'PASS' if results['latency_test'] else 'FAIL'}")
    print("=" * 60 + "\n")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Test BERT ONNX inference service"
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default="http://localhost:8080",
        help="Inference service endpoint URL"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for JSON results"
    )

    args = parser.parse_args()

    print(f"Testing endpoint: {args.endpoint}")

    client = BertInferenceClient(args.endpoint, args.timeout)
    results = run_test_scenarios(client)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {args.output}")

    # Exit with error code if any test failed
    all_passed = all([
        results["health_check"],
        results["single_inference"],
        results["batch_inference"],
        results["latency_test"]
    ])
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
