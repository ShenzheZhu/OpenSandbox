from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_CONFIG = REPO_ROOT / "dt_arena" / "config" / "env.yaml"
MCP_CONFIG = REPO_ROOT / "dt_arena" / "config" / "mcp.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_env_config() -> dict[str, Any]:
    return load_yaml(ENV_CONFIG)


def load_mcp_config() -> dict[str, Any]:
    return load_yaml(MCP_CONFIG)


def environments() -> dict[str, dict[str, Any]]:
    envs = load_env_config().get("environments") or {}
    if not isinstance(envs, dict):
        raise ValueError("env.yaml field 'environments' must be a mapping")
    return envs


def mcp_servers() -> list[dict[str, Any]]:
    servers = load_mcp_config().get("servers") or []
    if not isinstance(servers, list):
        raise ValueError("mcp.yaml field 'servers' must be a list")
    return servers


def get_environment(name: str) -> dict[str, Any]:
    envs = environments()
    if name not in envs:
        known = ", ".join(sorted(envs))
        raise KeyError(f"Unknown environment '{name}'. Known: {known}")
    return envs[name]


def get_mcp_server(name: str) -> dict[str, Any]:
    for server in mcp_servers():
        if server.get("name") == name:
            return server
    known = ", ".join(sorted(str(s.get("name")) for s in mcp_servers()))
    raise KeyError(f"Unknown MCP server '{name}'. Known: {known}")

