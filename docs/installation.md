# Installation

This guide covers different ways to install and set up Attach Gateway in your environment.

## Package Installation

### From PyPI (Recommended)

Install the base package:

```bash
pip install attach-dev
```

### With Memory Backend Support

For projects requiring persistent memory storage with Weaviate:

```bash
pip install "attach-dev[memory]"
```

For projects using Temporal workflows:

```bash
pip install "attach-dev[temporal]"
```

For development with all optional dependencies:

```bash
pip install "attach-dev[dev,memory,temporal]"
```

### From Source

Clone and install from the repository:

```bash
git clone https://github.com/attach-dev/attach-gateway.git
cd attach-gateway
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Configuration

### Memory Backend Options

By default, Attach runs with in-memory (non-persistent) storage. To use Weaviate:

```bash
pip install "attach-dev[memory]"
export MEM_BACKEND=weaviate
export WEAVIATE_URL=http://localhost:8081
attach-gateway  # starts with Weaviate support
```

### Environment Variables

Required for all setups:

```bash
export OIDC_ISSUER=https://YOUR_DOMAIN.auth0.com
export OIDC_AUD=your-api-identifier
```

Optional configuration:

```bash
export ENGINE_URL=http://localhost:11434  # Default: Ollama
export MEM_BACKEND=none                   # Options: none, weaviate, sakana
export WEAVIATE_URL=http://localhost:8081 # Required if MEM_BACKEND=weaviate
```

## Quick Start Verification

Test your installation:

```bash
python -c "import attach; print(attach.__version__)"
```

Run the gateway:

```bash
# Using the package command
attach-gateway

# Or directly with uvicorn
uvicorn attach.gateway:app --port 8080
```

## Docker Setup (Optional)

For memory persistence with Weaviate:

```bash
# Start Weaviate in Docker
python script/start_weaviate.py &

# Or manually
docker run -d -p 8081:8080 weaviate/weaviate:latest
```

## Troubleshooting

### Import Errors

If you encounter import errors, ensure you're using the correct memory backend:

```bash
# For auth-only mode (no memory persistence)
export MEM_BACKEND=none
python -c "import attach; print('✅ Installation verified')"
```

### Memory Backend Connection Issues

If Weaviate connection fails:

1. Verify Weaviate is running: `curl http://localhost:8081/v1/meta`
2. Check the WEAVIATE_URL environment variable
3. Try with `MEM_BACKEND=none` for testing

## Next Steps

- See [Examples](examples.md) for usage patterns
- Check [Agent Hand-offs](agent-handoffs/01-intro.md) for multi-agent setups
- Review [Design](design.md) for architecture details
