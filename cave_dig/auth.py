"""Einmal bei Google anmelden und das Token speichern.

Aufruf, im Projektordner:

    python -m cave_dig.auth

Der Browser geht auf. Du meldest dich mit dem Kanal an, der streamt, und
erlaubst das Lesen. Danach liegt tokens/youtube_token.json auf der Platte.
Diese Datei ist geheim. Sie steht in .gitignore.

Vorher in der Cloud Console eine Desktop-Client-ID anlegen und die JSON
als client_secret.json in diesen Ordner legen. Der Ablauf steht in der
ANLEITUNG.md.
"""

from __future__ import annotations

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from cave_dig.chat.youtube import SCOPES
from cave_dig.config import ConfigError, load_config
from cave_dig.logging_setup import setup_logging


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(exc)
        return 1
    setup_logging(config.log_dir)
    secrets = config.youtube_client_secrets
    if not secrets.exists():
        print(
            "client_secret.json fehlt.\n"
            "In der Google Cloud Console eine OAuth-Client-ID vom Typ Desktop anlegen,\n"
            "die JSON herunterladen und hier als client_secret.json speichern.\n"
            f"Erwartet unter: {secrets}"
        )
        return 1
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
    creds = flow.run_local_server(port=0)
    config.youtube_token_path.parent.mkdir(parents=True, exist_ok=True)
    config.youtube_token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"Token gespeichert: {config.youtube_token_path}")
    print("In config.yaml chat.provider auf youtube und chat.youtube.mode auf oauth setzen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
