import pytest
import os
import time
from unittest.mock import patch, MagicMock
import httpx
from jose import jwt

from auth.oidc import verify_jwt, _exchange_jwt_descope, _verify_jwt_direct, _fetch_jwks


class TestJWTVerification:
    """Test JWT verification functionality with mocked HTTP requests."""
    
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
            "iss": "https://api.descope.com/v1/apps/test-project",
            "aud": "test-project",
            "sub": "user-123",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "scope": "read write"
        }
    
    @pytest.fixture
    def env_vars_descope(self):
        """Set up environment variables for Descope backend."""
        env_vars = {
            "AUTH_BACKEND": "descope",
            "DESCOPE_PROJECT_ID": "test-project",
            "DESCOPE_CLIENT_ID": "test-client-id",
            "DESCOPE_CLIENT_SECRET": "test-client-secret",
            "DESCOPE_BASE_URL": "https://api.descope.com"
        }
        
        with patch.dict(os.environ, env_vars):
            yield env_vars
    
    @pytest.fixture
    def env_vars_mixed(self):
        """Set up environment variables for mixed backend."""
        env_vars = {
            "AUTH_BACKEND": "mixed",
            "OIDC_ISSUER_DESCOPE_TEST": "https://external-idp.com",
            "OIDC_AUD_DESCOPE_TEST": "test-audience",
            "DESCOPE_PROJECT_ID": "test-project",
            "DESCOPE_CLIENT_ID": "test-client-id",
            "DESCOPE_CLIENT_SECRET": "test-client-secret"
        }
        
        with patch.dict(os.environ, env_vars):
            yield env_vars

    @pytest.mark.asyncio
    async def test_exchange_jwt_descope_success(self, env_vars_descope, mock_descope_token_response):
        """Test successful JWT exchange with Descope."""
        with patch('httpx.AsyncClient') as mock_client:
            # Mock the async context manager
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_descope_token_response
            mock_response.raise_for_status.return_value = None
            mock_response.text = '{"access_token": "descope-jwt-token"}'
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            # Test the exchange
            external_jwt = "external.jwt.token"
            external_issuer = "https://external-idp.com"
            
            result = await _exchange_jwt_descope(external_jwt, external_issuer)
            
            assert result == "descope-jwt-token"
            
            # Verify the POST request was made correctly
            mock_client.return_value.__aenter__.return_value.post.assert_called_once()
            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            
            assert call_args[0][0] == "https://api.descope.com/oauth2/v1/apps/token"
            assert call_args[1]["data"]["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
            assert call_args[1]["data"]["assertion"] == external_jwt
            assert call_args[1]["data"]["client_id"] == "test-client-id"
            assert call_args[1]["data"]["issuer"] == external_issuer

    @pytest.mark.asyncio
    async def test_exchange_jwt_descope_failure(self, env_vars_descope):
        """Test JWT exchange failure handling."""
        with patch('httpx.AsyncClient') as mock_client:
            # Mock a failed response
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = '{"error": "invalid_grant"}'
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                message="400 Bad Request",
                request=MagicMock(),
                response=mock_response
            )
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            with pytest.raises(httpx.HTTPStatusError):
                await _exchange_jwt_descope("invalid.jwt.token", "https://external-idp.com")

    def test_fetch_jwks_descope_format(self, env_vars_descope, mock_jwks_response):
        """Test JWKS fetching for Descope format URLs."""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_jwks_response
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            issuer = "https://api.descope.com/v1/apps/test-project"
            result = _fetch_jwks(issuer)
            
            assert "keys" in result
            assert "ts" in result
            assert len(result["keys"]) == 1
            assert result["keys"][0]["kid"] == "test-key-id"
            
            # Verify correct JWKS URL was called
            mock_get.assert_called_once_with(
                "https://api.descope.com/test-project/.well-known/jwks.json",
                timeout=5
            )

    def test_fetch_jwks_standard_format(self, env_vars_mixed, mock_jwks_response):
        """Test JWKS fetching for standard OIDC format URLs."""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_jwks_response
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            issuer = "https://external-idp.com"
            result = _fetch_jwks(issuer)
            
            assert "keys" in result
            assert "ts" in result
            
            # Verify correct JWKS URL was called
            mock_get.assert_called_once_with(
                "https://external-idp.com/.well-known/jwks.json",
                timeout=5
            )

    @pytest.mark.asyncio
    async def test_verify_jwt_descope_backend_success(self, env_vars_descope, mock_jwks_response, sample_jwt_claims):
        """Test JWT verification in Descope-only mode."""
        with patch('httpx.get') as mock_get:
            # Mock JWKS response
            mock_response = MagicMock()
            mock_response.json.return_value = mock_jwks_response
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            # Mock JWT decode to return our sample claims
            with patch('jose.jwt.decode') as mock_decode:
                mock_decode.return_value = sample_jwt_claims
                
                # Mock JWT header inspection
                with patch('jose.jwt.get_unverified_header') as mock_header:
                    mock_header.return_value = {"alg": "RS256", "kid": "test-key-id"}
                    
                    result = await verify_jwt("test.jwt.token")
                    
                    assert result == sample_jwt_claims
                    assert result["iss"] == "https://api.descope.com/v1/apps/test-project"
                    assert result["aud"] == "test-project"

    @pytest.mark.asyncio
    async def test_verify_jwt_mixed_backend_fallback(self, env_vars_mixed, mock_jwks_response, 
                                                   mock_descope_token_response, sample_jwt_claims):
        """Test JWT verification in mixed mode with exchange fallback."""
        with patch('httpx.get') as mock_get:
            # Mock JWKS response
            mock_response = MagicMock()
            mock_response.json.return_value = mock_jwks_response
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            # Mock JWT decode to fail first (direct), then succeed (after exchange)
            with patch('jose.jwt.decode') as mock_decode:
                mock_decode.side_effect = [
                    ValueError("Direct verification failed"),  # First call fails
                    sample_jwt_claims  # Second call succeeds
                ]
                
                # Mock JWT header and claims inspection
                with patch('jose.jwt.get_unverified_header') as mock_header:
                    mock_header.return_value = {"alg": "RS256", "kid": "test-key-id"}
                    
                    with patch('jose.jwt.get_unverified_claims') as mock_claims:
                        mock_claims.return_value = {"iss": "https://external-idp.com"}
                        
                        # Mock the exchange call
                        with patch('httpx.AsyncClient') as mock_client:
                            mock_exchange_response = MagicMock()
                            mock_exchange_response.status_code = 200
                            mock_exchange_response.json.return_value = mock_descope_token_response
                            mock_exchange_response.raise_for_status.return_value = None
                            mock_exchange_response.text = '{"access_token": "descope-jwt-token"}'
                            
                            mock_client.return_value.__aenter__.return_value.post.return_value = mock_exchange_response
                            
                            result = await verify_jwt("external.jwt.token")
                            
                            assert result == sample_jwt_claims
                            # Verify exchange was called
                            mock_client.return_value.__aenter__.return_value.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_jwt_invalid_algorithm(self, env_vars_descope):
        """Test JWT verification with invalid algorithm."""
        with patch('jose.jwt.get_unverified_header') as mock_header:
            mock_header.return_value = {"alg": "HS256", "kid": "test-key-id"}
            
            with pytest.raises(ValueError, match="alg 'HS256' not allowed"):
                await verify_jwt("test.jwt.token")

    @pytest.mark.asyncio
    async def test_verify_jwt_missing_kid(self, env_vars_descope):
        """Test JWT verification with missing kid in header."""
        with patch('jose.jwt.get_unverified_header') as mock_header:
            mock_header.return_value = {"alg": "RS256"}
            
            with pytest.raises(ValueError, match="JWT header missing 'kid'"):
                await verify_jwt("test.jwt.token")

    def test_missing_env_vars(self):
        """Test that missing environment variables raise appropriate errors."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="OIDC_ISSUER must be set"):
                from auth.oidc import _get_oidc_issuer
                _get_oidc_issuer()

    @pytest.mark.asyncio
    async def test_verify_jwt_both_methods_fail(self, env_vars_mixed):
        """Test JWT verification when both direct and exchange methods fail."""
        with patch('jose.jwt.get_unverified_header') as mock_header:
            mock_header.return_value = {"alg": "RS256", "kid": "test-key-id"}
            
            with patch('jose.jwt.get_unverified_claims') as mock_claims:
                mock_claims.return_value = {"iss": "https://external-idp.com"}
                
                with patch('httpx.get') as mock_get:
                    mock_get.side_effect = httpx.HTTPStatusError(
                        message="404 Not Found",
                        request=MagicMock(),
                        response=MagicMock()
                    )
                    
                    with pytest.raises(ValueError, match="JWT verification failed"):
                        await verify_jwt("invalid.jwt.token")