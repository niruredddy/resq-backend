"""Supabase JWT validation and local-only role simulation."""
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException
from jwt import PyJWKClient

from app.config import settings

VALID_ROLES = {"commander", "logistics", "field_team", "analyst", "administrator"}


@lru_cache(maxsize=1)
def _jwks_client():
    return PyJWKClient(f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")


def get_actor(
    authorization: str | None = Header(default=None),
    x_demo_role: str | None = Header(default=None),
) -> dict:
    if (settings.app_env.lower() == "development" or settings.debug) and x_demo_role:
        role = (x_demo_role or "").strip().lower()
        if role in VALID_ROLES:
            return {"id": f"demo:{role}", "email": None, "role": role, "auth_mode": "demo"}

    if not settings.supabase_url and not settings.supabase_jwt_secret:
        if settings.app_env.lower() != "development" or not settings.debug:
            raise HTTPException(status_code=503, detail="Supabase authentication must be configured before production access is enabled.")
        role = (x_demo_role or "").strip().lower()
        if role not in VALID_ROLES:
            raise HTTPException(status_code=401, detail="Choose a local demo role to continue.")
        return {"id": f"demo:{role}", "email": None, "role": role, "auth_mode": "demo"}

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Supabase bearer token required.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        if settings.supabase_jwt_secret:
            claims = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
                issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
            )
        else:
            signing_key = _jwks_client().get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["ES256", "RS256"],
                audience="authenticated",
                issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
            )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Supabase token is invalid or expired.") from exc

    role = (claims.get("app_metadata") or {}).get("role")
    if role not in VALID_ROLES:
        raise HTTPException(status_code=403, detail="No authorized ResQ role is assigned to this account.")
    return {
        "id": claims.get("sub"),
        "email": claims.get("email"),
        "role": role,
        "auth_mode": "supabase",
    }


def require_roles(*roles):
    def dependency(actor=Depends(get_actor)):
        if actor["role"] not in roles and actor["role"] != "administrator":
            raise HTTPException(status_code=403, detail="This action is not available for your ResQ role.")
        return actor
    return dependency