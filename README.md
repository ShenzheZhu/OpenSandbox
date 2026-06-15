# OpenSandbox

Environment-only runtime extracted from the public
[AI-secure/DecodingTrust-Agent](https://github.com/AI-secure/DecodingTrust-Agent)
sandbox assets.

This repo intentionally keeps only:

- Docker Compose environment definitions.
- Environment-facing MCP server wrappers.
- A small lifecycle CLI for start, stop, reset, MCP launch, image pull, and image export.

It intentionally does not include benchmark task datasets, judges, agent runners, or environment mutation servers.

## Quick Start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .

opensandbox list-envs
opensandbox start gmail
opensandbox reset gmail
opensandbox mcp gmail --port 8853
opensandbox stop gmail --volumes
```

Docker images are still pulled from the upstream `decodingtrustagent/*` namespace unless a third-party image is listed in the compose file.

## Included Environments

The current import includes complete public compose assets for:

`arxiv`, `atlassian`, `bigquery`, `calendar`, `custom-website`, `customer_service`,
`databricks`, `ecommerce`, `gmail`, `google-form`, `googledocs`, `macos`,
`os-filesystem`, `paypal`, `salesforce`, `slack`, `snowflake`, `telegram`,
`telecom`, `terminal`, `travel`, `whatsapp`, `windows`, and `zoom`.

`macos` and `windows` are sanitized compose imports: listener sidecars used by the benchmark harness were removed. They still require local baseline VM disk directories.

## Offline Use

For environments that do not use Docker host networking:

```bash
opensandbox start bigquery --offline-network
```

This adds a Docker internal network override. If a compose file uses `network_mode: host`, the CLI refuses `--offline-network` because Docker cannot enforce per-container egress isolation in that mode. Run those inside a no-egress VM or convert the compose file to bridge networking first.

By default, the runtime scrubs common provider credentials such as `OPENAI_*`, `ANTHROPIC_*`, `REPLICATE_*`, Azure OpenAI, AWS, and Google application credentials from Docker/MCP subprocesses. Pass `--allow-host-env` only when you intentionally want host secrets inherited.

The imported compose files do not commit sandbox passwords or tokens. When a compose file marks a local-only secret as required, `opensandbox start` injects an ephemeral deterministic value for that Docker Compose project. If you run Docker Compose directly, set the required variables yourself.

## Image Export

To prepare an offline machine:

```bash
opensandbox pull gmail paypal calendar
opensandbox export-images outputs/opensandbox-core-images.tar gmail paypal calendar
```

Then load on the target machine:

```bash
docker load -i outputs/opensandbox-core-images.tar
```

## MCP

Start the environment first, then run its MCP wrapper:

```bash
opensandbox start paypal
opensandbox mcp paypal --port 8861
```

The MCP launcher reads `.opensandbox/state/*.json` to reuse the actual host ports assigned at environment start.

## Scope

This is an extraction/runtime scaffold, not a clean-room reimplementation of every simulated SaaS. Many services are still opaque prebuilt upstream Docker images. See [docs/PROVENANCE.md](docs/PROVENANCE.md).
