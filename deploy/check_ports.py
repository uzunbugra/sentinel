"""Fail if the rendered production compose config publishes a forbidden port.

SF-503 acceptance: apart from the reverse proxy (80/443), no service publishes a
port, and the development tools are not part of the production stack.

Usage (repository root):
    docker compose -f docker-compose.yml -f deploy/compose.prod.yml \
        --profile streaming --profile graph config --format json \
        | python deploy/check_ports.py
"""

from __future__ import annotations

import json
import sys

PROXY_SERVICE = "caddy"
PROXY_PORTS = {"80", "443"}
NEVER_IN_PRODUCTION = {"kafka-ui", "redis-commander", "prometheus"}


def problems(config: dict) -> list[str]:
    found: list[str] = []
    services = config.get("services", {})
    for name in sorted(NEVER_IN_PRODUCTION & services.keys()):
        found.append(f"{name}: development tool is part of the production stack")
    for name, service in sorted(services.items()):
        for port in service.get("ports") or []:
            published = str(port.get("published", "")) if isinstance(port, dict) else str(port)
            if name == PROXY_SERVICE and published in PROXY_PORTS:
                continue
            found.append(f"{name}: publishes {published or port}")
    return found


def main() -> int:
    config = json.load(sys.stdin)
    found = problems(config)
    services = ", ".join(sorted(config.get("services", {})))
    print(f"services: {services}")
    if found:
        print("FAIL")
        for line in found:
            print(f"  - {line}")
        return 1
    print("OK: no published ports except the reverse proxy (80/443)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
