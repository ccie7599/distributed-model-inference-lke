#!/usr/bin/env python3
"""
Load test script for BERT ONNX inference service.

Simulates concurrent requests to measure throughput and latency under load.

Usage:
    python load_test.py --endpoint http://localhost:8080 --concurrency 10 --requests 100
"""

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests
from transformers import BertTokenizer


@dataclass
class RequestResult:
    success: bool
    latency_ms: float
    status_code: int
    error: str = ""


class LoadTester:
    """Load tester for BERT inference service."""

    SAMPLE_TEXTS = [
        "The quick brown fox jumps over the lazy dog.",
        "Machine learning models can process natural language effectively.",
        "Kubernetes provides container orchestration at scale.",
        "BERT uses bidirectional training for language understanding.",
        "Cloud computing enables flexible infrastructure deployment.",
        "Neural networks learn patterns from large datasets.",
        "Microservices architecture improves application scalability.",
        "GPU acceleration speeds up deep learning inference.",
    ]

    def __init__(self, endpoint: str, timeout: int = 30):
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.tokenizer = BertTokenizer.from_pretrained("google-bert/bert-base-uncased")
        self._prepare_payloads()

    def _prepare_payloads(self):
        """Pre-tokenize sample texts for load testing."""
        self.payloads = []
        for text in self.SAMPLE_TEXTS:
            encoded = self.tokenizer(
                text,
                padding="max_length",
                truncation=True,
                max_length=128,
                return_tensors="np"
            )
            payload = {
                "inputs": {
                    "input_ids": encoded["input_ids"].tolist(),
                    "attention_mask": encoded["attention_mask"].tolist(),
                    "token_type_ids": encoded["token_type_ids"].tolist()
                }
            }
            self.payloads.append(payload)

    def _make_request(self, request_id: int) -> RequestResult:
        """Make a single inference request."""
        payload = self.payloads[request_id % len(self.payloads)]

        try:
            start_time = time.time()
            response = requests.post(
                f"{self.endpoint}/v1/models/bert:predict",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout
            )
            latency_ms = (time.time() - start_time) * 1000

            return RequestResult(
                success=response.status_code == 200,
                latency_ms=latency_ms,
                status_code=response.status_code
            )

        except requests.Timeout:
            return RequestResult(
                success=False,
                latency_ms=self.timeout * 1000,
                status_code=0,
                error="timeout"
            )
        except requests.RequestException as e:
            return RequestResult(
                success=False,
                latency_ms=0,
                status_code=0,
                error=str(e)
            )

    def run(self, num_requests: int, concurrency: int) -> dict:
        """Run load test with specified concurrency."""
        print(f"\nStarting load test:")
        print(f"  Endpoint: {self.endpoint}")
        print(f"  Total requests: {num_requests}")
        print(f"  Concurrency: {concurrency}")
        print("")

        results: list[RequestResult] = []
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(self._make_request, i): i
                for i in range(num_requests)
            }

            completed = 0
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                completed += 1

                # Progress update every 10%
                if completed % max(1, num_requests // 10) == 0:
                    pct = (completed / num_requests) * 100
                    print(f"  Progress: {completed}/{num_requests} ({pct:.0f}%)")

        total_time = time.time() - start_time

        return self._analyze_results(results, total_time, concurrency)

    def _analyze_results(
        self, results: list[RequestResult], total_time: float, concurrency: int
    ) -> dict:
        """Analyze load test results."""
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        latencies = [r.latency_ms for r in successful]

        analysis = {
            "summary": {
                "total_requests": len(results),
                "successful": len(successful),
                "failed": len(failed),
                "success_rate": len(successful) / len(results) * 100 if results else 0,
                "total_time_seconds": total_time,
                "requests_per_second": len(results) / total_time if total_time > 0 else 0,
                "concurrency": concurrency,
            },
            "latency_ms": {},
            "errors": {}
        }

        if latencies:
            sorted_latencies = sorted(latencies)
            analysis["latency_ms"] = {
                "min": min(latencies),
                "max": max(latencies),
                "mean": statistics.mean(latencies),
                "median": statistics.median(latencies),
                "stdev": statistics.stdev(latencies) if len(latencies) > 1 else 0,
                "p50": sorted_latencies[int(len(sorted_latencies) * 0.50)],
                "p90": sorted_latencies[int(len(sorted_latencies) * 0.90)],
                "p95": sorted_latencies[int(len(sorted_latencies) * 0.95)],
                "p99": sorted_latencies[int(len(sorted_latencies) * 0.99)],
            }

        # Categorize errors
        error_counts: dict[str, int] = {}
        for r in failed:
            error_key = r.error if r.error else f"http_{r.status_code}"
            error_counts[error_key] = error_counts.get(error_key, 0) + 1
        analysis["errors"] = error_counts

        return analysis


def print_report(analysis: dict):
    """Print formatted load test report."""
    print("\n" + "=" * 60)
    print(" Load Test Report")
    print("=" * 60)

    summary = analysis["summary"]
    print("\n[Summary]")
    print(f"  Total Requests:      {summary['total_requests']}")
    print(f"  Successful:          {summary['successful']}")
    print(f"  Failed:              {summary['failed']}")
    print(f"  Success Rate:        {summary['success_rate']:.2f}%")
    print(f"  Total Time:          {summary['total_time_seconds']:.2f}s")
    print(f"  Throughput:          {summary['requests_per_second']:.2f} req/s")
    print(f"  Concurrency:         {summary['concurrency']}")

    if analysis["latency_ms"]:
        lat = analysis["latency_ms"]
        print("\n[Latency (ms)]")
        print(f"  Min:                 {lat['min']:.2f}")
        print(f"  Max:                 {lat['max']:.2f}")
        print(f"  Mean:                {lat['mean']:.2f}")
        print(f"  Median:              {lat['median']:.2f}")
        print(f"  Std Dev:             {lat['stdev']:.2f}")
        print(f"  P50:                 {lat['p50']:.2f}")
        print(f"  P90:                 {lat['p90']:.2f}")
        print(f"  P95:                 {lat['p95']:.2f}")
        print(f"  P99:                 {lat['p99']:.2f}")

    if analysis["errors"]:
        print("\n[Errors]")
        for error, count in analysis["errors"].items():
            print(f"  {error}: {count}")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Load test BERT ONNX inference service"
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default="http://localhost:8080",
        help="Inference service endpoint URL"
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=100,
        help="Total number of requests to send"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent requests"
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

    tester = LoadTester(args.endpoint, args.timeout)
    analysis = tester.run(args.requests, args.concurrency)

    print_report(analysis)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(analysis, f, indent=2)
        print(f"\nResults saved to {args.output}")

    # Exit with error if success rate is below 95%
    if analysis["summary"]["success_rate"] < 95:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
