"""Fail if the rendered production compose config publishes a forbidden port.

SF-503 acceptance: apart from the reverse proxy (80/443), no service publishes a
port, and the development tools are not part of the production stack.
SF-505 acceptance: the web bundle is built against the public HTTPS/WSS origin
(no localhost), and the API allows only that origin for CORS.

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
LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "[::1]")


def _web_problems(services: dict) -> list[str]:
    found: list[str] = []
    args = ((services.get("frontend") or {}).get("build") or {}).get("args") or {}
    api_url = str(args.get("NEXT_PUBLIC_API_URL", ""))
    ws_url = str(args.get("NEXT_PUBLIC_WS_URL", ""))
    if "frontend" in services:
        if not api_url.startswith("https://"):
            found.append(f"frontend: NEXT_PUBLIC_API_URL must be https:// (got {api_url!r})")
        if not ws_url.startswith("wss://"):
            found.append(f"frontend: NEXT_PUBLIC_WS_URL must be wss:// (got {ws_url!r})")
        for name, url in (("NEXT_PUBLIC_API_URL", api_url), ("NEXT_PUBLIC_WS_URL", ws_url)):
            if any(host in url for host in LOCAL_HOSTS):
                found.append(f"frontend: {name} points at a local address ({url!r})")
    env = (services.get("api") or {}).get("environment") or {}
    if isinstance(env, list):
        env = dict(item.split("=", 1) for item in env if "=" in item)
    origins = [o.strip() for o in str(env.get("CORS_ORIGINS", "")).split(",") if o.strip()]
    if "api" in services:
        if not origins:
            found.append("api: CORS_ORIGINS is empty")
        for origin in origins:
            if not origin.startswith("https://") or any(h in origin for h in LOCAL_HOSTS):
                found.append(f"api: CORS origin {origin!r} is not a public https:// origin")
        expected = api_url.rstrip("/")
        if expected.startswith("https://") and origins and expected not in origins:
            found.append(
                f"api: CORS_ORIGINS {origins} does not include the web origin {expected!r}"
            )
    return found


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
    found.extend(_web_problems(services))
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
    print("OK: no published ports except the reverse proxy (80/443); web uses the public origin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
