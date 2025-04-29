import os, httpx, sys, json

resp = httpx.post(
    f"https://{os.getenv('AUTH0_DOMAIN')}/oauth/token",
    json={
        "client_id":     os.getenv("AUTH0_CLIENT"),
        "client_secret": os.getenv("AUTH0_SECRET"),  # add to .env
        "audience":      os.getenv("OIDC_AUD"),
        "grant_type":    "client_credentials",
    },
).json()

if "access_token" not in resp:
    sys.stderr.write(json.dumps(resp, indent=2) + "\n"); sys.exit(1)

print(resp["access_token"])
