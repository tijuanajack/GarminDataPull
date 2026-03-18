from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional
import os

from garminconnect import Garmin


class GarminAuthError(RuntimeError):
    """Raised when authentication cannot be completed."""


def _default_token_store_dir() -> Path:
    """Primary token cache location for new reads/writes."""
    return Path(__file__).parent / "data" / ".garminconnect"


def _legacy_token_store_dir() -> Path:
    """Legacy repo-root token cache location retained for backward compatibility."""
    return Path(__file__).resolve().parent.parent / "data" / ".garminconnect"


def _token_store_dir() -> Path:
    """Resolve where oauth token files are written.

    Defaults to `<repo>/garmin_agent/data/.garminconnect` to keep token state local
    to this repository, but can be overridden with `GARMIN_TOKEN_STORE_DIR`.
    """
    override = os.getenv("GARMIN_TOKEN_STORE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return _default_token_store_dir()


def _candidate_token_store_dirs() -> Iterable[Path]:
    """Return token directories to try when resuming an existing Garmin session."""
    override = os.getenv("GARMIN_TOKEN_STORE_DIR")
    if override:
        yield Path(override).expanduser().resolve()
        return

    seen: set[Path] = set()
    for path in (_default_token_store_dir(), _legacy_token_store_dir()):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        yield resolved


def _token_cache_mode() -> str:
    """Token mode: readwrite (default), readonly, or off."""
    mode = os.getenv("GARMIN_TOKEN_CACHE_MODE", "readwrite").strip().lower()
    return mode if mode in {"readwrite", "readonly", "off"} else "readwrite"

def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True when Garmin rejected auth with an HTTP 429/rate-limit response."""
    message = str(exc).lower()
    return "429" in message or "too many requests" in message


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
        for token_dir in _candidate_token_store_dirs():
            oauth1 = token_dir / "oauth1_token.json"
            oauth2 = token_dir / "oauth2_token.json"
            if not (oauth1.exists() and oauth2.exists()):
                continue
            try:
                g = Garmin()
                g.login(str(token_dir))
                return g
            except Exception as exc:
                if _is_rate_limit_error(exc):
                    raise GarminAuthError(
                        f"Garmin token refresh was rate-limited while using {token_dir}: {exc}"
                    ) from exc
                # Fall back to credential login below.
                pass

    try:
        g = Garmin(email=email, password=password, is_cn=False, return_on_mfa=True)
        state, session = g.login()
        if state == "needs_mfa":
            if not mfa:
                raise GarminAuthError("MFA required but GARMIN_MFA_CODE was not provided")
            g.resume_login(session, mfa)

        if can_write_tokens:
            write_targets = [store]
            if not os.getenv("GARMIN_TOKEN_STORE_DIR"):
                write_targets.append(_legacy_token_store_dir())

            seen: set[Path] = set()
            for target in write_targets:
                resolved = target.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                resolved.mkdir(parents=True, exist_ok=True)
                g.garth.dump(str(resolved))
        return g
    except Exception as exc:
        if _is_rate_limit_error(exc):
            raise GarminAuthError(
                "Garmin authentication was rate-limited (HTTP 429). Wait for Garmin to cool down or retry later. "
                f"Original error: {exc}"
            ) from exc
        raise GarminAuthError(f"Garmin authentication failed: {exc}") from exc
