from __future__ import annotations

import os
import time
from functools import lru_cache
from typing import Any
import asyncio
import httpx
import json
from jose import jwt
from dotenv import load_dotenv
load_dotenv()
from oidc import verify_jwt, _exchange_jwt_descope


async def test_token_exchange():
    """
    Test the inbound app exchange functionality.
    """
    """Test token exchange with freshly obtained Auth0 token."""
    
    print("Getting Auth0 token...")
    try:
        auth0_token = await get_auth0_token()
        print(f"✓ Got Auth0 token: {auth0_token[:50]}...")

        unverified_claims = jwt.get_unverified_claims(auth0_token)
        print(f"Token info:")
        print(f"   Issuer: {unverified_claims.get('iss')}")
        print(f"   Audience: {unverified_claims.get('aud')}")
        print(f"   Subject: {unverified_claims.get('sub')}")
        print(f"   Expires: {unverified_claims.get('exp')}")
        
    except Exception as e:
        print(f"✗ Failed to get Auth0 token: {e}")
        return
    
    print("\nTesting Auth0 token validation...")
    try:
        auth0_claims = await verify_jwt(auth0_token, leeway=60)
        print("✓ Auth0 token is valid")
        print(f"   Claims: {json.dumps(auth0_claims, indent=2)}")
    except Exception as e:
        print(f"✗ Auth0 token validation failed: {e}")
        return
    
    print("\nTesting token exchange...")
    try:
        descope_token = await _exchange_jwt_descope(
            external_jwt=auth0_token,
            external_issuer=f"https://{os.getenv('AUTH0_DOMAIN')}/",
        )
        print("✓ Token exchange successful")
        print(f"   Descope token: {descope_token[:50]}...")
        
        descope_claims = jwt.get_unverified_claims(descope_token)
        print(f"Descope token info:")
        print(f"   Issuer: {descope_claims.get('iss')}")
        print(f"   Audience: {descope_claims.get('aud')}")
        print(f"   Subject: {descope_claims.get('sub')}")
        
    except Exception as e:
        print(f"✗ Token exchange failed: {e}")
        return
    
    print("\nTesting Descope token verification...")
    try:
        final_claims = await verify_jwt(descope_token)
        print("✓ Descope token verification successful")
        print(f"   Final claims: {json.dumps(final_claims, indent=2)}")
    except Exception as e:
        print(f"✗ Descope token verification failed: {e}")
        return
    
    print("\nTesting end-to-end flow...")
    try:
        end_to_end_claims = await verify_jwt(auth0_token)
        print("✓ End-to-end authentication successful")
        print(f"   User authenticated as: {end_to_end_claims.get('sub')}")
    except Exception as e:
        print(f"✗ End-to-end authentication failed: {e}")


async def get_auth0_token() -> str:
    """
    Get a test token from Auth0 for testing purposes.
    """
    auth0_domain = os.getenv("AUTH0_DOMAIN")
    auth0_client_id = os.getenv("AUTH0_CLIENT_ID")  
    auth0_client_secret = os.getenv("AUTH0_CLIENT_SECRET")  
    auth0_audience = os.getenv("AUTH0_AUDIENCE")

    token_url = f"https://{auth0_domain}/oauth/token"

    token_data = {
        "client_id": auth0_client_id,
        "client_secret": auth0_client_secret,
        "audience": auth0_audience,
        "grant_type": "client_credentials"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            token_url,
            json=token_data,
            headers={"Content-Type": "application/json"}
        )
        
        response.raise_for_status()
        result = response.json()
        return result["access_token"]


asyncio.run(test_token_exchange())