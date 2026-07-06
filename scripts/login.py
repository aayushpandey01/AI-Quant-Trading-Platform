"""
Zerodha's access tokens expire every day at ~6am IST, so this login flow
has to be run once each trading day before using live/paper mode with real
data, or before scripts/load_historical_data.py.

Usage:
    python scripts/login.py
Follow the printed URL, log in, then paste the `request_token` from the
redirect URL back into the prompt. The resulting access token is written
to your .env file automatically.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import BASE_DIR, settings
from data.kite_client import KiteClient, KiteClientError


def update_env_file(access_token: str) -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        env_path.write_text(f"KITE_ACCESS_TOKEN={access_token}\n")
        return

    lines = env_path.read_text().splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith("KITE_ACCESS_TOKEN="):
            lines[i] = f"KITE_ACCESS_TOKEN={access_token}"
            found = True
            break
    if not found:
        lines.append(f"KITE_ACCESS_TOKEN={access_token}")
    env_path.write_text("\n".join(lines) + "\n")


def main():
    if not settings.kite_api_key or not settings.kite_api_secret:
        print("ERROR: Set KITE_API_KEY and KITE_API_SECRET in your .env file first.")
        sys.exit(1)

    client = KiteClient()
    login_url = client.get_login_url()
    print(f"\n1. Open this URL and log in with your Zerodha credentials:\n\n   {login_url}\n")
    print("2. After login you'll be redirected to your app's redirect URL, which will")
    print("   contain a 'request_token' query parameter. Copy that value.\n")

    request_token = input("Paste request_token here: ").strip()
    try:
        access_token = client.generate_session(request_token)
    except KiteClientError as exc:
        print(f"Login failed: {exc}")
        sys.exit(1)

    update_env_file(access_token)
    print(f"\nSuccess. Access token saved to .env for today's session.")


if __name__ == "__main__":
    main()
