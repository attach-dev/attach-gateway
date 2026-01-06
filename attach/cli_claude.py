"""
CLI helper for Claude Code MCP integration.

attach-gateway claude install --project <path>
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from mcp.config import get_enabled_servers


@click.group(name="claude")
def claude_group():
    """Claude Code integration helpers."""
    pass


@claude_group.command(name="install")
@click.option(
    "--project", default=".", help="Project directory (default: current directory)"
)
@click.option("--bearer", help="Bearer token for Authorization header (optional)")
@click.option(
    "--write-file", is_flag=True, help="Write .mcp.json file directly (experimental)"
)
def install_claude(project: str, bearer: str, write_file: bool):
    """
    Generate Claude Code MCP configuration.

    This command helps integrate Attach Gateway MCP servers with Claude Code.

    Default mode: Prints 'claude mcp add' commands to run.
    --write-file mode: Writes <project>/.mcp.json directly (experimental, schema may be outdated).
    """
    enabled = get_enabled_servers()

    if not enabled:
        click.echo(
            "No enabled MCP servers found. Use 'attach-gateway mcp add' to configure servers first.",
            err=True,
        )
        return

    # Get gateway URL from environment or default
    gateway_url = os.getenv("ATTACH_GATEWAY_URL", "http://localhost:8080")

    if write_file:
        _write_mcp_json_file(project, enabled, gateway_url, bearer)
    else:
        _print_claude_commands(enabled, gateway_url, bearer)


def _print_claude_commands(servers: dict, gateway_url: str, bearer: str):
    """Print 'claude mcp add' commands for each server."""
    click.echo("Run the following commands to add MCP servers to Claude Code:\n")

    for server_name in servers.keys():
        server_url = f"{gateway_url}/mcp/{server_name}"

        if bearer:
            # Check if Claude Code supports headers in HTTP transport
            click.echo(f"# Note: If Claude Code HTTP transport supports headers:")
            click.echo(
                f'claude mcp add --transport http --name "{server_name}" --url "{server_url}" --header "Authorization: Bearer {bearer}"'
            )
            click.echo()
            click.echo(
                f"# If headers are not supported, you'll need to configure auth separately or use a different approach."
            )
        else:
            click.echo(
                f'claude mcp add --transport http --name "{server_name}" --url "{server_url}"'
            )

        click.echo()

    if not bearer:
        click.echo(
            "Tip: Pass --bearer <token> to include Authorization header in commands (if supported by Claude)."
        )


def _write_mcp_json_file(
    project_dir: str, servers: dict, gateway_url: str, bearer: str
):
    """
    Write .mcp.json file for Claude Code (experimental).

    WARNING: This assumes a specific schema that may change.
    Prefer using 'claude mcp add' commands instead.
    """
    project_path = Path(project_dir).resolve()
    mcp_json_path = project_path / ".mcp.json"

    if mcp_json_path.exists():
        if not click.confirm(f"{mcp_json_path} already exists. Overwrite?"):
            click.echo("Aborted.")
            return

    # Build .mcp.json structure (this is experimental and may not match Claude's schema)
    mcp_config = {"mcpServers": {}}

    for server_name in servers.keys():
        server_url = f"{gateway_url}/mcp/{server_name}"

        server_config = {
            "transport": "http",
            "url": server_url,
        }

        if bearer:
            # This may not be the correct schema - Claude Code's HTTP transport may not support headers
            server_config["headers"] = {"Authorization": f"Bearer {bearer}"}
            click.echo(
                f"Warning: Added Authorization header, but Claude Code HTTP transport may not support headers.",
                err=True,
            )

        mcp_config["mcpServers"][server_name] = server_config

    try:
        with open(mcp_json_path, "w", encoding="utf-8") as f:
            json.dump(mcp_config, f, indent=2)

        click.echo(f"Wrote MCP configuration to {mcp_json_path}")
        click.echo()
        click.echo(
            "Note: This is experimental. The schema may not match Claude Code's requirements."
        )
        click.echo(
            "Prefer using 'claude mcp add' commands for guaranteed compatibility."
        )

    except IOError as exc:
        click.echo(f"Error writing {mcp_json_path}: {exc}", err=True)
