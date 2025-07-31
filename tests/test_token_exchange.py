import pytest
import os
import time
from unittest.mock import patch, MagicMock
import httpx
from jose import jwt

from auth.oidc import verify_jwt, verify_jwt_with_exchange, _exchange_jwt_descope, _verify_jwt_direct, _fetch_jwks


class TestJWTVerification:
    """Test JWT verification functionality with backward compatibility."""
    
    @pytest.fixture
    def mock_jwks_response(self):
        """Mock JWKS response data."""
        return {
            "keys": [
                {
                    "kid": "test-key-id",
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "n": "example-modulus",
                    "e": "AQAB"
                }
            ]
        }
    
    @pytest.fixture
    def mock_descope_token_response(self):
        """Mock Descope token exchange response."""
        return {
            "access_token": "descope-jwt-token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
    
    @pytest.fixture
    def sample_jwt_claims(self):
        """Sample JWT claims for testing."""
        return {
            "iss": "https://dev-test.auth0.com/",
            "aud": "test-audience",
            "sub": "user-123",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "scope": "read write"
        }
    
    @pytest.fixture
    def env_vars_auth0(self):
        """Set up environment variables for Auth0 (default/backward compatible)."""
        env_vars = {
            "OIDC_ISSUER": "https://dev-test.auth0.com/",
            "OIDC_AUD": "test-audience",
            "AUTH_BACKEND": "auth0",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            yield env_vars
    
    @pytest.fixture
    def env_vars_descope(self):
        """Set up environment variables for Descope backend."""
        env_vars = {
            "AUTH_BACKEND": "descope",
            "OIDC_ISSUER": "https://api.descope.com/v1/apps/test-project",
            "OIDC_AUD": "test-project",
            "DESCOPE_PROJECT_ID": "test-project",
            "DESCOPE_CLIENT_ID": "test-client-id",
            "DESCOPE_CLIENT_SECRET": "test-client-secret",
            "DESCOPE_BASE_URL": "https://api.descope.com"
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            yield env_vars

    def test_verify_jwt_backward_compatible(self, env_vars_auth0, mock_jwks_response, sample_jwt_claims):
        """Test that the original sync verify_jwt function still works (backward compatibility)."""
        with patch('httpx.get') as mock_get:
            # Mock JWKS response
            mock_response = MagicMock()
            mock_response.json.return_value = mock_jwks_response
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            with patch('jose.jwt.decode', return_value=sample_jwt_claims) as mock_decode:
                
                with patch('jose.jwt.get_unverified_header') as mock_header:
                    mock_header.return_value = {"alg": "RS256", "kid": "test-key-id"}
                    
                    result = verify_jwt("test.jwt.token")
                    
                    assert result == sample_jwt_claims
                    assert result["iss"] == "https://dev-test.auth0.com/"
                    assert result["aud"] == "test-audience"
                    
                    mock_decode.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_jwt_with_exchange_direct_success(self, env_vars_auth0, mock_jwks_response, sample_jwt_claims):
        """Test verify_jwt_with_exchange when direct verification succeeds."""
        with patch('httpx.get') as mock_get:
            # Mock JWKS response
            mock_response = MagicMock()
            mock_response.json.return_value = mock_jwks_response
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            with patch('jose.jwt.decode', return_value=sample_jwt_claims) as mock_decode:
                
                with patch('jose.jwt.get_unverified_header') as mock_header:
                    mock_header.return_value = {"alg": "RS256", "kid": "test-key-id"}
                    
                    result = await verify_jwt_with_exchange("test.jwt.token")
                    
                    assert result == sample_jwt_claims
                    mock_decode.assert_called_once()

    @pytest.mark.asyncio
    async def test_exchange_jwt_descope_success(self, mock_descope_token_response):
        """Test successful JWT exchange with Descope."""
        with patch.dict(os.environ, {
            "DESCOPE_PROJECT_ID": "test-project",
            "DESCOPE_CLIENT_ID": "test-client-id",
            "DESCOPE_CLIENT_SECRET": "test-client-secret"
        }):
            with patch('httpx.AsyncClient') as mock_client:
                # Mock the async context manager
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = mock_descope_token_response
                mock_response.raise_for_status.return_value = None
                
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                
                external_jwt = "external.jwt.token"
                external_issuer = "https://external-idp.com"
                
                result = await _exchange_jwt_descope(external_jwt, external_issuer)
                
                assert result == "descope-jwt-token"
                
                mock_client.return_value.__aenter__.return_value.post.assert_called_once()
                call_args = mock_client.return_value.__aenter__.return_value.post.call_args
                
                assert "oauth2/v1/apps/token" in call_args[0][0]
                assert call_args[1]["data"]["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
                assert call_args[1]["data"]["assertion"] == external_jwt
                assert call_args[1]["data"]["issuer"] == external_issuer

    @pytest.mark.asyncio
    async def test_verify_jwt_with_exchange_fallback(self, mock_jwks_response, mock_descope_token_response, sample_jwt_claims):
        """Test verify_jwt_with_exchange with fallback to token exchange."""
        env_vars = {
            "OIDC_ISSUER": "https://dev-test.auth0.com/",
            "OIDC_AUD": "test-audience",
            "ENABLE_DESCOPE_EXCHANGE": "true",
            "DESCOPE_PROJECT_ID": "test-project",
            "DESCOPE_CLIENT_ID": "test-client-id",
            "DESCOPE_CLIENT_SECRET": "test-client-secret"
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch('httpx.get') as mock_get:
                # Mock JWKS response
                mock_jwks_resp = MagicMock()
                mock_jwks_resp.json.return_value = mock_jwks_response
                mock_jwks_resp.raise_for_status.return_value = None
                mock_get.return_value = mock_jwks_resp
                
                with patch('jose.jwt.get_unverified_header') as mock_header:
                    mock_header.return_value = {"alg": "RS256", "kid": "test-key-id"}
                    
                    with patch('jose.jwt.get_unverified_claims') as mock_claims:
                        mock_claims.return_value = {"iss": "https://external-idp.com"}
                        
                        with patch('jose.jwt.decode') as mock_decode:
                            mock_decode.side_effect = [
                                ValueError("signing key not found in issuer JWKS"),  
                                sample_jwt_claims  
                            ]
                            
                            # Mock the Descope exchange
                            with patch('httpx.AsyncClient') as mock_client:
                                mock_exchange_response = MagicMock()
                                mock_exchange_response.status_code = 200
                                mock_exchange_response.json.return_value = mock_descope_token_response
                                mock_exchange_response.raise_for_status.return_value = None
                                
                                mock_client.return_value.__aenter__.return_value.post.return_value = mock_exchange_response
                                
                                result = await verify_jwt_with_exchange("external.jwt.token")
                                
                                assert result == sample_jwt_claims
      
                                mock_client.return_value.__aenter__.return_value.post.assert_called_once()

                                assert mock_decode.call_count == 2

    def test_auth_backend_defaults_to_auth0(self):
        """Test that AUTH_BACKEND defaults to 'auth0' for backward compatibility."""
        with patch.dict(os.environ, {}, clear=True):
            from auth.oidc import _get_auth_backend
            assert _get_auth_backend() == "auth0"

    def test_verify_jwt_invalid_algorithm(self, env_vars_auth0):
        """Test JWT verification with invalid algorithm."""
        with patch('jose.jwt.get_unverified_header') as mock_header:
            mock_header.return_value = {"alg": "HS256", "kid": "test-key-id"}
            
            with pytest.raises(ValueError, match="alg 'HS256' not allowed"):
                verify_jwt("test.jwt.token")  # Test sync version

    @pytest.mark.asyncio
    async def test_verify_jwt_with_exchange_invalid_algorithm(self, env_vars_auth0):
        """Test JWT verification with invalid algorithm on async version."""
        with patch('jose.jwt.get_unverified_header') as mock_header:
            mock_header.return_value = {"alg": "HS256", "kid": "test-key-id"}
            
            with pytest.raises(ValueError, match="alg 'HS256' not allowed"):
                await verify_jwt_with_exchange("test.jwt.token")  # Test async version