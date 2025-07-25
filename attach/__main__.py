"""
CLI entry point - replaces the need for main.py in wheel
"""
import uvicorn
import click

def main():
    """Run Attach Gateway server"""
    # Load .env file if it exists (for development)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # python-dotenv not installed, that's OK for production
    
    @click.command()
    @click.option("--host", default="0.0.0.0", help="Host to bind to")
    @click.option("--port", default=8080, help="Port to bind to") 
    @click.option("--reload", is_flag=True, help="Enable auto-reload")
    def cli(host: str, port: int, reload: bool):
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
    
    cli()

def _friendly_exit(err):
    """Convert RuntimeError to clean user message."""
    err_str = str(err)
    
    if "OPENMETER_API_KEY" in err_str:
        msg = (f"❌ {err}\n\n"
               "💡 Fix:\n"
               "   export OPENMETER_API_KEY=\"sk_live_...\"\n"
               "   (or) export USAGE_METERING=null    # to disable metering\n\n"
               "📖 See README.md for complete setup")
    else:
        msg = (f"❌ {err}\n\n"
               "💡 Required environment variables:\n"
               "   export OIDC_ISSUER=\"https://your-domain.auth0.com/\"\n"
               "   export OIDC_AUD=\"your-api-identifier\"\n\n"
               "📖 See README.md for complete setup instructions")
    
    raise click.ClickException(msg)

if __name__ == "__main__":
    main() 