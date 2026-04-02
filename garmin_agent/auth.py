from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional
import contextlib
import inspect
import os

from garminconnect import Garmin
from dotenv import load_dotenv


class GarminAuthError(RuntimeError):
    """Raised when authentication cannot be completed."""


def load_local_env() -> None:
    """Load optional local .env files for non-CI runs."""
    script_dir = Path(__file__).parent
    load_dotenv(script_dir / ".env")
    load_dotenv(script_dir.parent / ".env")


def _token_store_dir() -> Path:
    """Resolve where oauth token files are read/written.

    Defaults to `<repo>/garmin_agent/data/.garminconnect` to keep token state local
    to this repository, but can be overridden with `GARMIN_TOKEN_STORE_DIR`.
    """
    override = os.getenv("GARMIN_TOKEN_STORE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).parent / "data" / ".garminconnect"


def _token_store_file() -> Path:
    return _token_store_dir() / "garmin_tokens.json"


def _token_cache_mode() -> str:
    """Token mode: readwrite (default), readonly, or off."""
    mode = os.getenv("GARMIN_TOKEN_CACHE_MODE", "readwrite").strip().lower()
    return mode if mode in {"readwrite", "readonly", "off"} else "readwrite"


def _supports_parameter(callable_obj, name: str) -> bool:
    try:
        return name in inspect.signature(callable_obj).parameters
    except (TypeError, ValueError):
        return False


def _resolve_mfa_prompt(mfa: Optional[str]) -> Optional[Callable[[], str]]:
    if mfa:
        code = mfa.strip()
        if code:
            return lambda: code

    if os.getenv("GITHUB_ACTIONS") == "true":
        return None

    if os.getenv("GARMIN_INTERACTIVE_MFA", "true").strip().lower() in {"0", "false", "no", "off"}:
        return None

    def prompt() -> str:
        return input("Enter Garmin MFA code: ").strip()

    return prompt


def _new_garmin_with_credentials(email: str, password: str, mfa: Optional[str]) -> Garmin:
    kwargs = {"email": email, "password": password}
    prompt_mfa = _resolve_mfa_prompt(mfa)

    # Legacy parameter (still supported by older releases).
    if _supports_parameter(Garmin.__init__, "is_cn"):
        kwargs["is_cn"] = False

    # New API prefers prompt_mfa callback.
    if _supports_parameter(Garmin.__init__, "prompt_mfa"):
        if prompt_mfa:
            kwargs["prompt_mfa"] = prompt_mfa
    # Legacy MFA flow.
    elif _supports_parameter(Garmin.__init__, "return_on_mfa"):
        kwargs["return_on_mfa"] = True

    return Garmin(**kwargs)


def _call_login(g: Garmin, store: Path | None):
    """Call Garmin.login in a way that supports old and new library versions."""
    if store is None:
        return g.login()
    os.environ["GARMINTOKENS"] = str(store)
    try:
        return g.login(str(store))
    except TypeError:
        # Older versions expect no args and require explicit token dump.
        return g.login()


def _prime_tokenstore_path(g: Garmin, store: Path | None) -> None:
    """Ensure modern clients know where to persist refreshed tokens."""
    if store is None:
        return
    client = getattr(g, "client", None)
    if client is not None and hasattr(client, "_tokenstore_path"):
        client._tokenstore_path = str(store)


def _persist_tokens(g: Garmin, store: Path | None) -> None:
    """Persist tokens for both modern and legacy auth clients."""
    if store is None:
        return

    store.parent.mkdir(parents=True, exist_ok=True)

    client = getattr(g, "client", None)
    if client is not None and hasattr(client, "dump"):
        with contextlib.suppress(Exception):
            client.dump(str(store))

    if hasattr(g, "garth"):
        with contextlib.suppress(Exception):
            g.garth.dump(str(store.parent))


def login(email: Optional[str] = None, password: Optional[str] = None, mfa: Optional[str] = None) -> Garmin:
    """Authenticate with Garmin using token cache + credential fallback.

    Modes:
      - readwrite: try token login; on credential login success, persist tokens.
      - readonly: try token login; credential login allowed but tokens not persisted.
      - off: skip token login and never write token files.

    Supports both old garth-based auth and the newer mobile-SSO flow.
    """
    mode = _token_cache_mode()
    store = _token_store_file()
    can_read_tokens = mode in {"readwrite", "readonly"}
    can_write_tokens = mode == "readwrite"

    if can_read_tokens:
        try:
            g = Garmin()
            _call_login(g, store)
            return g
        except Exception as exc:
            if os.getenv("GITHUB_ACTIONS") == "true":
                raise GarminAuthError(f"Token-based login failed: {exc}") from exc

    if not email or not password:
        raise GarminAuthError(
            "Token-based login failed and no GARMIN_EMAIL/GARMIN_PASSWORD were provided "
            "for credential fallback. Set them in your shell or in GarminDataPull/.env."
        )

    try:
        g = _new_garmin_with_credentials(email, password, mfa)
        _prime_tokenstore_path(g, store if can_write_tokens else None)

        login_result = _call_login(g, store if can_write_tokens else None)

        # Legacy MFA handshake path.
        if isinstance(login_result, tuple) and len(login_result) == 2:
            state, session = login_result
            if state == "needs_mfa":
                if not mfa:
                    raise GarminAuthError("MFA required but GARMIN_MFA_CODE was not provided")
                if not hasattr(g, "resume_login"):
                    raise GarminAuthError("MFA required but library does not support resume_login")
                g.resume_login(session, mfa)

        if can_write_tokens:
            _persist_tokens(g, store)
        return g
    except Exception as exc:
        raise GarminAuthError(f"Garmin authentication failed: {exc}") from exc


def main() -> None:
    load_local_env()
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    mfa = os.getenv("GARMIN_MFA_CODE")
    login(email, password, mfa)
    print(f"Authenticated with Garmin. Token store: {_token_store_file()}")


if __name__ == "__main__":
    main()
