from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional
import os

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


class GarminAuthError(RuntimeError):
    """Raised when authentication cannot be completed."""


def _token_store_dir() -> Path:
    """Resolve where OAuth token files are read/written.

    Priority:
      1) GARMIN_TOKEN_STORE_DIR (project variable)
      2) GARMINTOKENS (upstream garminconnect variable)
      3) <repo>/garmin_agent/data/.garminconnect
    """
    override = os.getenv("GARMIN_TOKEN_STORE_DIR") or os.getenv("GARMINTOKENS")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).parent / "data" / ".garminconnect"


def _token_cache_mode() -> str:
    """Token mode: readwrite (default), readonly, or off."""
    mode = os.getenv("GARMIN_TOKEN_CACHE_MODE", "readwrite").strip().lower()
    return mode if mode in {"readwrite", "readonly", "off"} else "readwrite"


def _prompt_mfa_from_env(mfa: Optional[str]) -> Callable[[], str]:
    """Return a callback used by python-garminconnect when MFA is required."""

    def prompt_mfa() -> str:
        code = (mfa or "").strip()
        if not code:
            raise GarminAuthError("MFA required but GARMIN_MFA_CODE was not provided")
        return code

    return prompt_mfa


def login(email: str, password: str, mfa: Optional[str] = None) -> Garmin:
    """Authenticate with Garmin using current python-garminconnect mobile SSO flow.

    Modes:
      - readwrite: try token login; on credential login success, persist tokens.
      - readonly: try token login; credential login allowed but tokens not persisted.
      - off: skip token login and never write token files.

    Notes:
      - New auth stores tokens in `<token_store_dir>/garmin_tokens.json`.
      - `garmin.login(tokenstore_path)` handles both restore and fresh-login persistence.
    """
    mode = _token_cache_mode()
    store = _token_store_dir()
    can_read_tokens = mode in {"readwrite", "readonly"}
    can_write_tokens = mode == "readwrite"

    if can_read_tokens:
        try:
            g = Garmin()
            g.login(str(store))
            return g
        except GarminConnectTooManyRequestsError as exc:
            raise GarminAuthError(f"Garmin rate limit during token login: {exc}") from exc
        except (GarminConnectAuthenticationError, GarminConnectConnectionError):
            if os.getenv("GITHUB_ACTIONS") == "true":
                raise GarminAuthError("Token-based login failed in CI; refresh token cache first")

    try:
        g = Garmin(
            email=email,
            password=password,
            is_cn=False,
            prompt_mfa=_prompt_mfa_from_env(mfa),
        )
        token_path = str(store) if can_write_tokens else None
        g.login(token_path)
        return g
    except GarminConnectTooManyRequestsError as exc:
        raise GarminAuthError(f"Garmin rate limit during credential login: {exc}") from exc
    except GarminAuthError:
        raise
    except Exception as exc:
        raise GarminAuthError(f"Garmin authentication failed: {exc}") from exc
