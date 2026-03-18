from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional
import os

from garth.exc import GarthException, GarthHTTPError
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


class GarminAuthError(RuntimeError):
    """Raised when authentication cannot be completed."""


def _default_token_store_dir() -> Path:
    """Project-local token directory used when no env override is provided."""
    return Path(__file__).parent / "data" / ".garminconnect"


def _legacy_token_store_dir() -> Path:
    """Legacy repo-root token directory kept as a read-only fallback."""
    return Path(__file__).resolve().parent.parent / "data" / ".garminconnect"


def _token_store_dir() -> Path:
    """Resolve the canonical token directory.

    Upstream python-garminconnect uses `GARMINTOKENS`; keep `GARMIN_TOKEN_STORE_DIR`
    as a backward-compatible alias for this repository.
    """
    override = os.getenv("GARMINTOKENS") or os.getenv("GARMIN_TOKEN_STORE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return _default_token_store_dir().resolve()


def _candidate_token_store_dirs() -> Iterable[Path]:
    """Return token directories to try, prioritizing the canonical upstream path."""
    primary = _token_store_dir()
    seen: set[Path] = {primary}
    yield primary

    if os.getenv("GARMINTOKENS") or os.getenv("GARMIN_TOKEN_STORE_DIR"):
        return

    legacy = _legacy_token_store_dir().resolve()
    if legacy not in seen:
        yield legacy


def _has_token_files(token_dir: Path) -> bool:
    """Check whether the directory looks like a garth token store."""
    return (token_dir / "oauth1_token.json").exists() and (token_dir / "oauth2_token.json").exists()


def login(email: str, password: str, mfa: Optional[str] = None) -> Garmin:
    """Authenticate with Garmin using the current upstream token flow first.

    The upstream project now centers auth around a single token directory configured via
    `GARMINTOKENS`, with credential login used only when cached tokens are unavailable
    or invalid. This helper mirrors that behavior while still reading the repository's
    legacy `data/.garminconnect` directory as a fallback.
    """
    token_store = _token_store_dir()

    for token_dir in _candidate_token_store_dirs():
        if not _has_token_files(token_dir):
            continue
        try:
            g = Garmin()
            g.login(str(token_dir))
            return g
        except GarminConnectTooManyRequestsError as exc:
            raise GarminAuthError(
                "Garmin rate-limited token refresh. Reusing cached tokens is still the right path, "
                f"but Garmin rejected the refresh for {token_dir}: {exc}"
            ) from exc
        except (
            FileNotFoundError,
            GarthHTTPError,
            GarminConnectAuthenticationError,
            GarminConnectConnectionError,
        ):
            continue

    try:
        g = Garmin(email=email, password=password, is_cn=False, return_on_mfa=True)
        state, session = g.login()
        if state == "needs_mfa":
            if not mfa:
                raise GarminAuthError("MFA required but GARMIN_MFA_CODE was not provided")
            g.resume_login(session, mfa)

        token_store.mkdir(parents=True, exist_ok=True)
        g.garth.dump(str(token_store))
        return g
    except GarminConnectTooManyRequestsError as exc:
        raise GarminAuthError(
            "Garmin rate-limited credential login. Avoid repeated fresh logins in CI and wait before retrying. "
            f"Original error: {exc}"
        ) from exc
    except (GarminAuthError, GarminConnectAuthenticationError, GarminConnectConnectionError, GarthException) as exc:
        raise GarminAuthError(f"Garmin authentication failed: {exc}") from exc
