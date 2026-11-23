"""Tests for deploy/check_ports.py (SF-503 ports, SF-505 web origin)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "deploy" / "check_ports.py"
_spec = importlib.util.spec_from_file_location("check_ports", _PATH)
assert _spec and _spec.loader
check_ports = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_ports)


def _config(**overrides: dict) -> dict:
    services = {
        "caddy": {"ports": [{"published": "80"}, {"published": "443"}]},
        "postgres": {"ports": []},
        "api": {"environment": {"CORS_ORIGINS": "https://sentinel.example.org"}},
        "frontend": {
            "build": {
                "args": {
                    "NEXT_PUBLIC_API_URL": "https://sentinel.example.org",
                    "NEXT_PUBLIC_WS_URL": "wss://sentinel.example.org",
                }
            }
        },
    }
    services.update(overrides)
    return {"services": services}


def test_production_config_passes() -> None:
    assert check_ports.problems(_config()) == []


def test_published_infra_port_fails() -> None:
    found = check_ports.problems(_config(postgres={"ports": [{"published": "5432"}]}))
    assert found == ["postgres: publishes 5432"]


def test_dev_tool_in_stack_fails() -> None:
    found = check_ports.problems(_config(**{"kafka-ui": {}}))
    assert any("kafka-ui" in line for line in found)


def test_localhost_web_build_fails() -> None:
    frontend = {
        "build": {
            "args": {
                "NEXT_PUBLIC_API_URL": "http://localhost:8000",
                "NEXT_PUBLIC_WS_URL": "ws://localhost:8000",
            }
        }
    }
    found = check_ports.problems(_config(frontend=frontend))
    assert any("NEXT_PUBLIC_API_URL must be https://" in line for line in found)
    assert any("NEXT_PUBLIC_WS_URL must be wss://" in line for line in found)
    assert any("local address" in line for line in found)


def test_cors_must_match_web_origin() -> None:
    api = {"environment": {"CORS_ORIGINS": "https://other.example.org"}}
    found = check_ports.problems(_config(api=api))
    assert any("does not include the web origin" in line for line in found)


def test_localhost_cors_fails() -> None:
    api = {"environment": ["CORS_ORIGINS=http://localhost:3000"]}
    found = check_ports.problems(_config(api=api))
    assert any("not a public https:// origin" in line for line in found)
