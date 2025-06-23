# Flask Integration Example

This example shows how to integrate Attach Gateway with a Flask application.

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp ../../.env.example .env
# Edit .env with your OIDC settings
```

## Run

```bash
# 1. Start Attach Gateway (in another terminal)
attach-gateway

# 2. Start Flask app
python app.py

# 3. Test the integration
curl -H "Authorization: Bearer $YOUR_JWT" \
     -H "Content-Type: application/json" \
     -d '{"model":"tinyllama","prompt":"hello"}' \
     http://localhost:5000/chat
```

## How it works

1. Flask app receives requests with JWT tokens
2. Forwards requests to Attach Gateway at localhost:8080
3. Gateway validates JWT and proxies to your LLM engine
4. Response streams back through Gateway → Flask → Client 