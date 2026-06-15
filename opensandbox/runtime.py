from __future__ import annotations

import json
import os
import re
import hashlib
import shlex
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Iterable

import yaml

from .config import MCP_CONFIG, REPO_ROOT, get_environment, get_mcp_server, load_mcp_config


STATE_DIR = REPO_ROOT / ".opensandbox" / "state"

BLOCKED_ENV_PREFIXES = (
    "OPENAI_",
    "ANTHROPIC_",
    "REPLICATE_",
    "AZURE_OPENAI_",
    "SEMANTIC_SCHOLAR",
)
BLOCKED_ENV_NAMES = {
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
}
PASSTHROUGH_ENV = {
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "TMPDIR",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_CONFIG",
    "SSH_AUTH_SOCK",
}


def ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_").lower()


def project_name(prefix: str, env_name: str) -> str:
    return sanitize_name(f"{prefix}_{env_name}")


def state_path(project: str) -> Path:
    ensure_state_dir()
    return STATE_DIR / f"{project}.json"


def compose_path(env_cfg: dict[str, Any]) -> Path:
    path = REPO_ROOT / str(env_cfg["docker_compose"])
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def load_state(project: str) -> dict[str, Any] | None:
    path = state_path(project)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(project: str, state: dict[str, Any]) -> None:
    state_path(project).write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def remove_state(project: str) -> None:
    path = state_path(project)
    if path.exists():
        path.unlink()


def is_blocked_env(name: str) -> bool:
    return name in BLOCKED_ENV_NAMES or any(name.startswith(prefix) for prefix in BLOCKED_ENV_PREFIXES)


def subprocess_env(extra: dict[str, str], allow_host_env: bool = False) -> dict[str, str]:
    if allow_host_env:
        env = dict(os.environ)
    else:
        env = {k: v for k, v in os.environ.items() if k in PASSTHROUGH_ENV}
    if not allow_host_env:
        for key in list(env):
            if is_blocked_env(key):
                env.pop(key, None)
    env.update({k: str(v) for k, v in extra.items()})
    if not allow_host_env:
        for key in list(env):
            if is_blocked_env(key) and key not in extra:
                env.pop(key, None)
    return env


REQUIRED_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*):\?[^}]*\}")
SENSITIVE_ENV_RE = re.compile(r"(PASSWORD|PASS|SECRET|TOKEN|API_KEYS?|KEY|SALT)", re.IGNORECASE)


def generated_local_value(name: str, project: str) -> str:
    digest = hashlib.sha256(f"{project}:{name}".encode("utf-8")).hexdigest()[:12]
    return f"opensandbox-local-{name.lower().replace('_', '-')}-{digest}"


def compose_required_env(compose_file: Path, project: str) -> dict[str, str]:
    text = compose_file.read_text(encoding="utf-8")
    values: dict[str, str] = {}
    for name in sorted(set(REQUIRED_ENV_RE.findall(text))):
        if name in os.environ:
            values[name] = os.environ[name]
        elif SENSITIVE_ENV_RE.search(name):
            values[name] = generated_local_value(name, project)
        else:
            values[name] = ""
    return values


def run(cmd: list[str], cwd: Path, env: dict[str, str], check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(shlex.quote(c) for c in cmd), file=sys.stderr)
    return subprocess.run(cmd, cwd=str(cwd), env=env, text=True, check=check)


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def allocate_port(default: int, used: set[int]) -> int:
    candidate = default
    while candidate < 65535:
        if candidate not in used and port_free(candidate):
            used.add(candidate)
            return candidate
        candidate += 1
    raise RuntimeError(f"Could not allocate a free port starting at {default}")


def allocate_ports(env_cfg: dict[str, Any], fixed: bool = False, used: set[int] | None = None) -> dict[str, str]:
    used = used if used is not None else set()
    allocated: dict[str, str] = {}
    ports = env_cfg.get("ports") or {}
    if not isinstance(ports, dict):
        return allocated
    for name, meta in ports.items():
        default = int((meta or {}).get("default", 0) or 0)
        if default <= 0:
            continue
        port = default if fixed else allocate_port(default, used)
        if fixed:
            used.add(port)
        allocated[name] = str(port)
    return allocated


def has_host_network(compose_file: Path) -> bool:
    data = yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}
    for service in (data.get("services") or {}).values():
        if isinstance(service, dict) and service.get("network_mode") == "host":
            return True
    return False


def offline_override(project: str) -> Path:
    path = STATE_DIR / f"{project}.offline-network.yml"
    path.write_text("networks:\n  default:\n    internal: true\n", encoding="utf-8")
    return path


def compose_command(project: str, compose_file: Path, offline_network: bool) -> list[str]:
    cmd = ["docker", "compose", "-p", project, "-f", str(compose_file)]
    if offline_network:
        cmd.extend(["-f", str(offline_override(project))])
    return cmd


def start_environment(
    env_name: str,
    prefix: str = "opensandbox",
    fixed_ports: bool = False,
    offline_network: bool = False,
    allow_host_env: bool = False,
) -> dict[str, Any]:
    ensure_state_dir()
    cfg = get_environment(env_name)
    compose_file = compose_path(cfg)
    if offline_network and has_host_network(compose_file):
        raise RuntimeError(
            f"{env_name} uses network_mode: host, so Docker internal networks cannot enforce offline mode. "
            "Run without --offline-network, or first convert this compose file to bridge networking."
        )
    project = project_name(prefix, env_name)
    ports = allocate_ports(cfg, fixed=fixed_ports)
    required = compose_required_env(compose_file, project)
    env = subprocess_env({**required, **ports}, allow_host_env=allow_host_env)
    cmd = compose_command(project, compose_file, offline_network) + ["up", "-d", "--remove-orphans"]
    run(cmd, cwd=compose_file.parent, env=env)
    state = {
        "environment": env_name,
        "project": project,
        "compose_file": str(compose_file.relative_to(REPO_ROOT)),
        "ports": ports,
        "offline_network": offline_network,
        "started_at": int(time.time()),
    }
    save_state(project, state)
    return state


def stop_environment(env_name: str, prefix: str = "opensandbox", volumes: bool = False) -> None:
    project = project_name(prefix, env_name)
    state = load_state(project)
    cfg = get_environment(env_name)
    compose_file = compose_path(cfg)
    required = compose_required_env(compose_file, project)
    env = subprocess_env({**required, **((state or {}).get("ports", {}))})
    cmd = compose_command(project, compose_file, bool((state or {}).get("offline_network"))) + ["down", "--remove-orphans"]
    if volumes:
        cmd.append("--volumes")
    run(cmd, cwd=compose_file.parent, env=env, check=False)
    remove_state(project)


def replace_vars(value: str, mapping: dict[str, str]) -> str:
    pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}|\$([A-Za-z_][A-Za-z0-9_]*)")

    def repl(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(3)
        default = match.group(2)
        return str(mapping.get(name, default if default is not None else os.environ.get(name, "")))

    return pattern.sub(repl, value)


def resolve_mapping(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, str):
        return replace_vars(value, mapping)
    if isinstance(value, list):
        return [resolve_mapping(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: resolve_mapping(v, mapping) for k, v in value.items()}
    return value


def reset_environment(env_name: str, prefix: str = "opensandbox") -> list[str]:
    project = project_name(prefix, env_name)
    state = load_state(project)
    cfg = get_environment(env_name)
    ports = dict((state or {}).get("ports") or {})
    if not ports:
        ports = allocate_ports(cfg, fixed=True)
    endpoints = cfg.get("reset_endpoints") or {}
    results: list[str] = []
    for name, endpoint in endpoints.items():
        url = replace_vars(str(endpoint.get("url")), ports)
        method = str(endpoint.get("method", "POST")).upper()
        req = urllib.request.Request(url, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                results.append(f"{name}: {resp.status} {url}")
        except Exception as exc:  # pragma: no cover - depends on running containers
            results.append(f"{name}: ERROR {url}: {exc}")
    if not results:
        results.append(f"{env_name}: no reset endpoint configured")
    return results


def list_images(env_names: Iterable[str]) -> list[str]:
    images: list[str] = []
    for env_name in env_names:
        cfg = get_environment(env_name)
        compose_file = compose_path(cfg)
        proc = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "config", "--images"],
            cwd=str(compose_file.parent),
            text=True,
            capture_output=True,
            env=subprocess_env(compose_required_env(compose_file, project_name("opensandbox", env_name))),
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"Could not list images for {env_name}")
        images.extend(line.strip() for line in proc.stdout.splitlines() if line.strip())
    return sorted(set(images))


def pull_images(env_names: Iterable[str]) -> None:
    for env_name in env_names:
        cfg = get_environment(env_name)
        compose_file = compose_path(cfg)
        run(
            ["docker", "compose", "-f", str(compose_file), "pull"],
            cwd=compose_file.parent,
            env=subprocess_env(compose_required_env(compose_file, project_name("opensandbox", env_name))),
        )


def export_images(env_names: Iterable[str], output_tar: Path) -> None:
    images = list_images(env_names)
    if not images:
        raise RuntimeError("No images found")
    output_tar.parent.mkdir(parents=True, exist_ok=True)
    run(["docker", "save", "-o", str(output_tar), *images], cwd=REPO_ROOT, env=subprocess_env({}))


def mcp_environment_names(server: dict[str, Any]) -> list[str]:
    env = server.get("environment")
    if env is None:
        return []
    if isinstance(env, list):
        return [str(e) for e in env]
    return [str(env)]


def mcp_port(server: dict[str, Any], requested: int | None = None) -> str:
    if requested:
        return str(requested)
    default = int(server.get("port") or 0)
    if default <= 0:
        return "0"
    return str(default if port_free(default) else allocate_port(default, set()))


def run_mcp_server(
    server_name: str,
    prefix: str = "opensandbox",
    port: int | None = None,
    allow_host_env: bool = False,
) -> None:
    server = get_mcp_server(server_name)
    mapping: dict[str, str] = {}
    for env_name in mcp_environment_names(server):
        state = load_state(project_name(prefix, env_name))
        env_cfg_for_server = get_environment(env_name)
        compose_file_for_server = compose_path(env_cfg_for_server)
        required = compose_required_env(compose_file_for_server, project_name(prefix, env_name))
        mapping.update(required)
        if state:
            mapping.update({k: str(v) for k, v in (state.get("ports") or {}).items()})
            mapping[f"{sanitize_name(env_name).upper().replace('-', '_')}_PROJECT_NAME"] = str(state.get("project"))
        else:
            mapping.update(allocate_ports(env_cfg_for_server, fixed=True))
            mapping[f"{sanitize_name(env_name).upper().replace('-', '_')}_PROJECT_NAME"] = project_name(prefix, env_name)

    env_cfg = resolve_mapping(server.get("env") or {}, mapping)
    env_cfg["PORT"] = mcp_port(server, port)
    env_cfg["HOST"] = str(env_cfg.get("HOST", "0.0.0.0"))

    command = resolve_mapping(server.get("command") or ["python3", Path(str(server["path"])).name], env_cfg)
    path = Path(str(server["path"]))
    cwd = (MCP_CONFIG.parent / str(load_mcp_config().get("global", {}).get("base_dir", "../mcp_server")) / path.parent).resolve()
    if not cwd.exists():
        raise FileNotFoundError(cwd)
    run([str(c) for c in command], cwd=cwd, env=subprocess_env({k: str(v) for k, v in env_cfg.items()}, allow_host_env))
