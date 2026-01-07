"""
CLI commands for MCP server management.

attach-gateway mcp list
attach-gateway mcp add <name> <url>
attach-gateway mcp enable <name>
attach-gateway mcp disable <name>
attach-gateway mcp remove <name>
"""

from __future__ import annotations

import click

from attach.mcp.config import (
    get_mcp_config_path,
    load_mcp_config,
    save_mcp_config,
)


@click.group(name="mcp")
def mcp_group():
    """Manage MCP servers."""
    pass


@mcp_group.command(name="list")
def list_servers():
    """List all configured MCP servers."""
    config = load_mcp_config()
    servers = config.get("servers", {})

    if not servers:
        click.echo("No MCP servers configured.")
        click.echo(f"Config file: {get_mcp_config_path()}")
        return

    click.echo(f"MCP servers ({get_mcp_config_path()}):\n")
    for name, server_config in servers.items():
        enabled = server_config.get("enabled", False)
        url = server_config.get("url", "")
        status = "✓ enabled" if enabled else "✗ disabled"
        click.echo(f"  {name:20} {status:12} {url}")


@mcp_group.command(name="add")
@click.argument("name")
@click.argument("url")
@click.option(
    "--header", multiple=True, help="Header in format 'Key: Value' or 'Key: env:VAR'"
)
def add_server(name: str, url: str, header: tuple[str, ...]):
    """Add a new MCP server."""
    config = load_mcp_config()

    if name in config.get("servers", {}):
        if not click.confirm(f"Server '{name}' already exists. Overwrite?"):
            click.echo("Aborted.")
            return

    # Parse headers
    headers = {}
    for h in header:
        if ": " not in h:
            click.echo(f"Warning: Invalid header format '{h}', skipping", err=True)
            continue
        key, value = h.split(": ", 1)
        headers[key] = value

    config.setdefault("servers", {})[name] = {
        "enabled": True,
        "url": url,
    }

    if headers:
        config["servers"][name]["headers"] = headers

    save_mcp_config(config)
    click.echo(f"Added MCP server '{name}'")
    click.echo(f"  URL: {url}")
    if headers:
        click.echo(f"  Headers: {list(headers.keys())}")


@mcp_group.command(name="enable")
@click.argument("name")
def enable_server(name: str):
    """Enable an MCP server."""
    config = load_mcp_config()

    if name not in config.get("servers", {}):
        click.echo(f"Error: Server '{name}' not found", err=True)
        return

    config["servers"][name]["enabled"] = True
    save_mcp_config(config)
    click.echo(f"Enabled MCP server '{name}'")


@mcp_group.command(name="disable")
@click.argument("name")
def disable_server(name: str):
    """Disable an MCP server."""
    config = load_mcp_config()

    if name not in config.get("servers", {}):
        click.echo(f"Error: Server '{name}' not found", err=True)
        return

    config["servers"][name]["enabled"] = False
    save_mcp_config(config)
    click.echo(f"Disabled MCP server '{name}'")


@mcp_group.command(name="remove")
@click.argument("name")
def remove_server(name: str):
    """Remove an MCP server."""
    config = load_mcp_config()

    if name not in config.get("servers", {}):
        click.echo(f"Error: Server '{name}' not found", err=True)
        return

    if not click.confirm(f"Remove server '{name}'?"):
        click.echo("Aborted.")
        return

    del config["servers"][name]
    save_mcp_config(config)
    click.echo(f"Removed MCP server '{name}'")
