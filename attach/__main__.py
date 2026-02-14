"""
CLI entry point - replaces the need for main.py in wheel
"""

import click
import uvicorn


def main():
    """Run Attach Gateway server"""
    # Load .env file if it exists (for development)
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass  # python-dotenv not installed, that's OK for production

    # Import subcommand groups
    from .cli_claude import claude_group
    from .cli_mcp import mcp_group

    @click.group(invoke_without_command=True)
    @click.option("--host", default="0.0.0.0", help="Host to bind to")
    @click.option("--port", default=8080, help="Port to bind to")
    @click.option("--reload", is_flag=True, help="Enable auto-reload")
    @click.pass_context
    def cli(ctx, host: str, port: int, reload: bool):
        """Attach Gateway - Identity & Memory side-car for LLM engines"""
        # If no subcommand, run the server (backward compatibility)
        if ctx.invoked_subcommand is None:
            try:
                # Import here AFTER .env is loaded and CLI is parsed
                from .gateway import create_app

                app = create_app()
                uvicorn.run(app, host=host, port=port, reload=reload)
            except RuntimeError as e:
                _friendly_exit(e)
            except Exception as e:  # unexpected crash
                click.echo(f"❌ Startup failed: {e}", err=True)
                raise click.Abort()

    # Add subcommand groups
    cli.add_command(mcp_group)
    cli.add_command(claude_group)

    cli()


def _friendly_exit(err):
    """Convert RuntimeError to clean user message."""
    msg = (
        f"❌ {err}\n\n"
        "💡 Required environment variables:\n"
        '   export OIDC_ISSUER="https://your-domain.auth0.com/"\n'
        '   export OIDC_AUD="your-api-identifier"\n\n'
        "📖 See README.md for complete setup instructions"
    )

    raise click.ClickException(msg)


if __name__ == "__main__":
    main()
