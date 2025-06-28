# Examples

## demo2.html (Planner ↔ Coder UI)

Follow the steps in the HTML comment at the top of `demo2.html`
to start the gateway, both agents and the static web-page.

## Viewing memory

This example uses the **Docker-based** Weaviate server started by
`script/start_weaviate.py`, so no cloud signup is required.

## Web Framework Integration

### [Flask App](flask_app/)
Basic Flask application showing JWT forwarding to Attach Gateway.

```bash
cd examples/flask_app
pip install -r requirements.txt
python app.py
```

## Terminal Testing

### Option A: With Auth0 Credentials

If you have Auth0 set up:

```bash
# 1. Set your Auth0 credentials  
export AUTH0_DOMAIN=your-domain.auth0.com
export AUTH0_CLIENT=your-client-id
export AUTH0_SECRET=your-client-secret
export OIDC_ISSUER=https://your-domain.auth0.com
export OIDC_AUD=your-api-identifier
export MEM_BACKEND=weaviate
export WEAVIATE_URL=http://localhost:8081

# 2. Start weaviate (required for memory storage)
# Manual Docker (recommended, works on all platforms including Mac M1/M2):
docker run --rm -p 6666:8080 \
  -e QUERY_DEFAULTS_LIMIT=25 \
  -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true \
  -e PERSISTENCE_DATA_PATH="/var/lib/weaviate" \
  -e DEFAULT_VECTORIZER_MODULE="none" \
  -e CLUSTER_HOSTNAME="node1" \
  semitechnologies/weaviate:1.30.5 &

# Alternative: Use script (may not work on Mac M1/M2)
python script/start_weaviate.py

# Then start other services:
ollama serve                    # separate terminal
attach-gateway --port 8080     # separate terminal

# 3. Get JWT and test
JWT="<your-app-generated-jwt-token>"
curl -H "Authorization: Bearer $JWT" \
     -H "Content-Type: application/json" \
     -d '{"model":"tinyllama","prompt":"Hello!"}' \
     http://localhost:8080/api/chat
```

### Option B: Auth-only Mode (No Memory)

For testing without Weaviate:

```bash
# Minimal setup - just auth verification
export OIDC_ISSUER=https://your-domain.auth0.com
export OIDC_AUD=your-api-identifier
export MEM_BACKEND=none  # No memory backend

attach-gateway --port 8080
# Test with your JWT...
```

**Don't have Auth0?** See the [Flask example](flask_app/) for integration patterns, or check Auth0's free tier setup.

# Just install the missing dependency
pip install "weaviate-client>=3.26.7,<4"

# Then try again
attach-gateway --port 8080
