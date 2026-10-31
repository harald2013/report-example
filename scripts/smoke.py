#!/usr/bin/env python3
"""Exercise a real deployment; optionally restart only the local demo worker."""

import argparse
import json
import os
import subprocess
import time
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restart-worker", action="store_true")
    args = parser.parse_args()
    base = os.getenv("API_BASE_URL", "http://127.0.0.1:18000").rstrip("/")
    headers = {"Content-Type": "application/json"}
    if token := os.getenv("API_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    def request(path, body=None):
        req = Request(base + path, headers=headers,
                      data=json.dumps(body).encode() if body is not None else None)
        with urlopen(req, timeout=15) as response:
            return json.load(response)

    assert request("/ready")["status"] == "ready"
    job = request("/reports", {"values": [10, 20, 30],
                               "delay_seconds": 30 if args.restart_worker else 1})
    if args.restart_worker:
        # Wait for the first database activity before interrupting the timer.
        for _ in range(60):
            state = request(job["url"])
            if state.get("report"):
                break
            time.sleep(1)
        else:
            raise RuntimeError("Worker did not start the report")
        subprocess.run(["docker", "compose", "restart", "worker"], check=True)
    for _ in range(120):
        result = request(job["url"])
        if result["status"] == "completed":
            assert result["result"] == {
                "count": 3, "sum": 60, "min": 10, "max": 30, "mean": 20,
            }, result
            listed = request("/reports?limit=100")["items"]
            assert result in listed, "Completed report missing from GET /reports"
            print(f"Report {job['id']}: completed; database result verified")
            return
        if result["status"] in {"failed", "timed_out", "terminated", "canceled"}:
            raise RuntimeError(f"Report failed: {result['status']}")
        time.sleep(1)
    raise TimeoutError("Report did not complete")


if __name__ == "__main__":
    main()
