from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config import environments, mcp_servers
from .runtime import (
    export_images,
    list_images,
    project_name,
    pull_images,
    reset_environment,
    run_mcp_server,
    start_environment,
    stop_environment,
)


def cmd_list_envs(_: argparse.Namespace) -> int:
    rows = []
    for name, cfg in sorted(environments().items()):
        rows.append(
            {
                "name": name,
                "profile": cfg.get("profile", ""),
                "compose": cfg.get("docker_compose", ""),
                "ports": sorted((cfg.get("ports") or {}).keys()),
            }
        )
    print(json.dumps(rows, indent=2))
    return 0


def cmd_list_mcp(_: argparse.Namespace) -> int:
    rows = []
    for server in mcp_servers():
        rows.append(
            {
                "name": server.get("name"),
                "environment": server.get("environment"),
                "path": server.get("path"),
                "port": server.get("port"),
            }
        )
    print(json.dumps(rows, indent=2))
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    used: list[dict[str, Any]] = []
    for env_name in args.environments:
        state = start_environment(
            env_name,
            prefix=args.prefix,
            fixed_ports=args.fixed_ports,
            offline_network=args.offline_network,
            allow_host_env=args.allow_host_env,
        )
        used.append(state)
    print(json.dumps(used, indent=2, sort_keys=True))
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    for env_name in args.environments:
        stop_environment(env_name, prefix=args.prefix, volumes=args.volumes)
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    for env_name in args.environments:
        for line in reset_environment(env_name, prefix=args.prefix):
            print(line)
    return 0


def cmd_images(args: argparse.Namespace) -> int:
    print("\n".join(list_images(args.environments)))
    return 0


def cmd_pull(args: argparse.Namespace) -> int:
    pull_images(args.environments)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    export_images(args.environments, Path(args.output))
    print(args.output)
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    run_mcp_server(args.server, prefix=args.prefix, port=args.port, allow_host_env=args.allow_host_env)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opensandbox")
    parser.add_argument("--prefix", default="opensandbox", help="Docker Compose project prefix")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list-envs", help="List imported environments")
    p.set_defaults(func=cmd_list_envs)

    p = sub.add_parser("list-mcp", help="List imported MCP servers")
    p.set_defaults(func=cmd_list_mcp)

    p = sub.add_parser("start", help="Start one or more environments")
    p.add_argument("environments", nargs="+")
    p.add_argument("--fixed-ports", action="store_true", help="Use configured default ports exactly")
    p.add_argument("--offline-network", action="store_true", help="Use a Docker internal network when compose supports it")
    p.add_argument("--allow-host-env", action="store_true", help="Pass host environment variables through to Docker")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("stop", help="Stop one or more environments")
    p.add_argument("environments", nargs="+")
    p.add_argument("--volumes", action="store_true", help="Remove Docker volumes")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("reset", help="Call reset endpoints for running environments")
    p.add_argument("environments", nargs="+")
    p.set_defaults(func=cmd_reset)

    p = sub.add_parser("images", help="Print Docker images needed by environments")
    p.add_argument("environments", nargs="+")
    p.set_defaults(func=cmd_images)

    p = sub.add_parser("pull", help="Pull Docker images for environments")
    p.add_argument("environments", nargs="+")
    p.set_defaults(func=cmd_pull)

    p = sub.add_parser("export-images", help="Save environment Docker images to a tar archive")
    p.add_argument("output")
    p.add_argument("environments", nargs="+")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("mcp", help="Run an MCP server in the foreground")
    p.add_argument("server")
    p.add_argument("--port", type=int)
    p.add_argument("--allow-host-env", action="store_true", help="Pass host environment variables through to the MCP process")
    p.set_defaults(func=cmd_mcp)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        parser.exit(1, f"opensandbox: error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
