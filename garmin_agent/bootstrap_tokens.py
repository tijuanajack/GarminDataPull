from __future__ import annotations

import argparse
from getpass import getpass
import os

from auth import GarminAuthError, login, _token_store_dir


def _prompt_env(name: str, label: str, secret: bool = False) -> str:
    current = os.getenv(name)
    if current:
        return current
    value = getpass(f"{label}: ") if secret else input(f"{label}: ").strip()
    if not value:
        raise SystemExit(f"{name} is required")
    os.environ[name] = value
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactively create or refresh Garmin OAuth tokens."
    )
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Try the existing token cache before forcing a fresh username/password + MFA login.",
    )
    args = parser.parse_args()

    email = _prompt_env("GARMIN_EMAIL", "Garmin email")
    password = _prompt_env("GARMIN_PASSWORD", "Garmin password", secret=True)

    try:
        login(email, password, force_reauth=not args.reuse_existing)
    except GarminAuthError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"✅ Garmin tokens saved to {_token_store_dir()}")
    if args.reuse_existing:
        print("Existing cached tokens were allowed; if Garmin required MFA, you were prompted for it.")
    else:
        print("A fresh Garmin login was forced, so this is the best command to use when you want to re-enter MFA.")
    print("You can now rerun the GitHub workflow or copy/cache that folder for CI.")


if __name__ == "__main__":
    main()
