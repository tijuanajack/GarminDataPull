from __future__ import annotations

from pathlib import Path
from typing import Optional
import os

from garminconnect import Garmin


class GarminAuthError(RuntimeError):
    """Raised when authentication cannot be completed."""


def _token_store_dir() -> Path:
    """Resolve where oauth token files are read/written.

    Defaults to `<repo>/garmin_agent/data/.garminconnect` to keep token state local
    to this repository, but can be overridden with `GARMIN_TOKEN_STORE_DIR`.
    """
    override = os.getenv("GARMIN_TOKEN_STORE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).parent / "data" / ".garminconnect"


def _token_cache_mode() -> str:
    """Token mode: readwrite (default), readonly, or off."""
    mode = os.getenv("GARMIN_TOKEN_CACHE_MODE", "readwrite").strip().lower()
    return mode if mode in {"readwrite", "readonly", "off"} else "readwrite"


def login(email: str, password: str, mfa: Optional[str] = None) -> Garmin:
    """Authenticate with Garmin using token cache + credential fallback.

    Modes:
      - readwrite: try token login; on credential login success, persist tokens.
      - readonly: try token login; credential login allowed but tokens not persisted.
      - off: skip token login and never write token files.
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
        except Exception as exc:
            if os.getenv("GITHUB_ACTIONS") == "true":
                raise GarminAuthError(f"Token-based login failed: {exc}") from exc

    try:
        def prompt_mfa() -> str:
            if not mfa:
                raise GarminAuthError("MFA required but GARMIN_MFA_CODE was not provided")
            return mfa

        g = Garmin(email=email, password=password, prompt_mfa=prompt_mfa)
        if can_write_tokens:
            store.mkdir(parents=True, exist_ok=True)
            g.login(str(store))
        else:
            g.login()
        return g
    except Exception as exc:
        raise GarminAuthError(f"Garmin authentication failed: {exc}") from exc
