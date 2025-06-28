"""
CLI entry point - replaces the need for main.py in wheel
"""
import uvicorn
from .gateway import create_app

def main():
    """Run Attach Gateway server"""
    # Load .env file if it exists (for development)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # python-dotenv not installed, that's OK for production
    
    import click
    
    @click.command()
    @click.option("--host", default="0.0.0.0", help="Host to bind to")
    @click.option("--port", default=8080, help="Port to bind to") 
    @click.option("--reload", is_flag=True, help="Enable auto-reload")
    def cli(host: str, port: int, reload: bool):
        app = create_app()
        uvicorn.run(app, host=host, port=port, reload=reload)
    
    cli()

if __name__ == "__main__":
    main() 