"""Authenticated, non-destructive pre-flight check for a live Aegis demo."""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_json(url: str, key: str | None) -> dict:
    headers = {"X-API-Key": key} if key else {}
    with urlopen(Request(url, headers=headers), timeout=10) as response:  # nosec B310 -- operator-supplied localhost endpoint
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--api-key", default=os.getenv("AEGIS_API_KEY"))
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    try:
        readiness = request_json(f"{base}/readyz", None)
        pipeline = request_json(f"{base}/pipeline/stats", args.api_key)
    except (HTTPError, URLError, TimeoutError) as exc:
        print(json.dumps({"result": "FAIL", "reason": type(exc).__name__}))
        return 2
    checks = readiness.get("checks", {})
    required = ("database", "base_detector", "tracking", "evidence_storage", "redis", "api_authentication")
    failed = [name for name in required if checks.get(name, {}).get("status") not in {"ok", "skip"}]
    stages = pipeline.get("stages", [])
    stopped = [item.get("name") for item in stages if not item.get("running")]
    result = "PASS" if not failed and not stopped else "DEGRADED" if readiness.get("status") != "not_ready" else "FAIL"
    print(json.dumps({"result": result, "readiness": readiness.get("status"), "failed_checks": failed, "stopped_stages": stopped}, indent=2))
    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
