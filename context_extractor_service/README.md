# Context extractor service

The context extractor is AIST's authenticated MCP service for source-aware AI
analysis. It does not accept arbitrary file uploads or fetch source URLs.
Instead, every source tool receives a `pipeline_id` and a relative path.

## Runtime boundary

For each request the service:

1. resolves the active pipeline through the AIST internal API;
2. obtains the pipeline's authorized project root;
3. validates the requested relative path beneath that root;
4. reads the source from the Compose read-only project-workspace mount;
5. returns bounded structural or textual context.

`AIST_API_TOKEN` authenticates the service to the platform. `MCP_AUTH_TOKEN`
protects the MCP HTTP endpoint and is required in production deployments.

## Tool groups

The MCP surface provides:

- function extraction, AST inspection, and identifier analysis;
- definitions, callers, imports, decorators, and route discovery;
- configuration and environment analysis;
- bounded file read, search, and directory listing.

Tree-sitter language support and extraction behavior live in the implementation
package under `ansible/files/context_extractor/`. See
[`ansible/files/README.md`](ansible/files/README.md) for development and test
commands.

## Deployment

Docker Compose builds `ansible/files/Dockerfile`, exposes streamable HTTP on
port 8000 inside the application network, and mounts
`/tmp/aist/projects` read-only. The service is long-lived; pipeline workspaces
remain operation-scoped and are removed by the owning pipeline lifecycle.
