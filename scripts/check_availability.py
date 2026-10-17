"""One-shot HTTPS readiness check for an external scheduler; no credentials needed."""
import argparse
from datetime import datetime, timezone
import json
from urllib.parse import urlsplit
from urllib.request import urlopen


def check(origin: str) -> bool:
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("Use an HTTPS origin, for example https://ranch.example.com")
    try:
        with urlopen(origin.rstrip("/") + "/health/ready", timeout=10) as response:
            return response.status == 200 and json.loads(response.read(4096)).get("status") == "ready"
    except Exception:
        # Never print a response body, URL credentials or database/network exception.
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin", help="Public HTTPS origin without a path")
    args = parser.parse_args()
    try:
        ready = check(args.origin)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({"checked_at": datetime.now(timezone.utc).isoformat(), "ready": ready}))
    raise SystemExit(0 if ready else 1)


if __name__ == "__main__":
    main()
