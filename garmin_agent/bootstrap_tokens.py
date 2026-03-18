from __future__ import annotations

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
    email = _prompt_env("GARMIN_EMAIL", "Garmin email")
    password = _prompt_env("GARMIN_PASSWORD", "Garmin password", secret=True)

    try:
        login(email, password)
    except GarminAuthError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"✅ Garmin tokens saved to {_token_store_dir()}")
    print("You can now rerun the GitHub workflow or copy/cache that folder for CI.")


if __name__ == "__main__":
    main()
