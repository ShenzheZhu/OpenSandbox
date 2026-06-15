# Provenance

Source snapshot:

- Repository: `AI-secure/DecodingTrust-Agent`
- License file copied from upstream: `Apache-2.0`
- Imported paths: selected `dt_arena/envs`, selected `dt_arena/mcp_server`, and filtered `dt_arena/config`

Not imported:

- `dataset/`
- `benchmark/`
- `eval/`
- root-level `utils/` task execution helpers
- `dt_arena/injection_mcp_server/`
- `dt_arena/config/injection_mcp.yaml`
- local judge/evaluation helpers under `dt_arena/utils`, except the minimal terminal container-name helper required by the terminal MCP

Quarantined for later cleanup:

- `finance`: local MCP tree contains benchmark-specific adversarial presets and related web extraction logic.
- `legal`: local MCP tree contains environment mutation support intertwined with the normal server.
- `ers`: compose references a missing local `hrms/docker` volume in the public repo snapshot.
- `research`: MCP server includes external academic API clients and separate safety-evaluation helpers. The local `arxiv` environment is imported without that MCP server.
- `hospital`: compose passes external model-provider credentials into the container.
- `reddit`, `googlesheets`, `googledrive`, `github`, `gitlab`, `x`, `chase`, `robinhood`, `booking`, `doordash`, `expedia`, `southwest`, `united`: public snapshot lacks complete compose/build context or uses incomplete local build assets.

Known upstream third-party bases:

- `axllent/mailpit` for the Gmail mail sandbox.
- `ghcr.io/goccy/bigquery-emulator` for BigQuery.
- `dockur`-derived Windows/macOS images via `decodingtrustagent/windows` and `decodingtrustagent/macos`.

