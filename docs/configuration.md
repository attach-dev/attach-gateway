# Configuration Guide

## Environment Variables

Attach Gateway reads configuration from environment variables or `.env` files.

### Quick Setup

```bash
# Copy template and edit
cp .env.example .env
# Edit .env with your values
```

### Variable Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OIDC_ISSUER` | ✅ | - | Your OIDC provider URL |
| `OIDC_AUD` | ✅ | - | JWT audience claim |
| `ENGINE_URL` | ❌ | `http://localhost:11434` | Target LLM engine |
| `MEM_BACKEND` | ❌ | `none` | Memory backend (`none`, `weaviate`, `sakana`) |
| `WEAVIATE_URL` | ❌ | - | Required if `MEM_BACKEND=weaviate` |

### Environment-Specific Configs

**Development (.env.development):**
```bash
OIDC_ISSUER=https://dev.auth0.com
OIDC_AUD=dev-api
MEM_BACKEND=none  # Fast local dev
ENGINE_URL=http://localhost:11434
```

**Production (.env.production):**
```bash
OIDC_ISSUER=https://prod.auth0.com
OIDC_AUD=prod-api
MEM_BACKEND=weaviate
WEAVIATE_URL=https://weaviate-cluster.com
ENGINE_URL=https://vllm-prod.internal:8000
```

### Best Practices

1. **Never commit .env files** (add to .gitignore)
2. **Use python-dotenv** for local development
3. **Validate required variables** on startup
4. **Use different configs** per environment

## Integration Examples

See working code examples in the [examples/](../examples/) folder:

- **[Flask Integration](../examples/flask_app/)** - Complete Flask app with JWT forwarding
- **[Memory Demo](../examples/demo_view_memory.py)** - View stored conversations 