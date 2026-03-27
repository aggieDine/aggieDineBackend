import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwk, jwt

from app.config import settings

security = HTTPBearer()

_jwks_cache: dict | None = None


async def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(settings.cognito_jwks_url)
            resp.raise_for_status()
            _jwks_cache = resp.json()
    return _jwks_cache


def _get_public_key(token: str, jwks: dict):
    headers = jwt.get_unverified_headers(token)
    kid = headers.get("kid")
    for key in jwks.get("keys", []):
        if key["kid"] == kid:
            return jwk.construct(key)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Public key not found",
    )


async def verify_cognito_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    try:
        jwks = await _get_jwks()
        public_key = _get_public_key(token, jwks)
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.AWS_COGNITO_APP_CLIENT_ID,
            issuer=settings.cognito_issuer,
        )
        return claims
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not fetch JWKS",
        )


async def get_current_user(
    claims: dict = Depends(verify_cognito_token),
) -> dict:
    return {
        "sub": claims.get("sub"),
        "email": claims.get("email"),
        "groups": claims.get("cognito:groups", []),
    }
