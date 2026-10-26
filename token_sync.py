"""
Synchronise les jetons Garmin entre le disque du conteneur Render et Supabase.

Pourquoi : le disque Render est effacé à chaque redémarrage. Les jetons
renouvelés par la bibliothèque Garmin pendant que le serveur tourne sont donc
perdus, et le serveur redémarre avec les vieux jetons de GARMIN_TOKENS_B64.
Ici, chaque nouvelle version du fichier est recopiée dans Supabase, et c'est
elle qu'on recharge au démarrage.

Usage :
    python token_sync.py pull   -> au démarrage : Supabase -> disque
                                   (secours : variable GARMIN_TOKENS_B64)
    python token_sync.py watch  -> en arrière-plan : disque -> Supabase
                                   dès que le fichier change

Variables d'environnement :
    SUPABASE_URL               ex. https://xxxx.supabase.co
    SUPABASE_SERVICE_ROLE_KEY  clé service_role (Project Settings > API)
    GARMIN_TOKENS_B64          (optionnel) secours si Supabase est vide/injoignable
    GARMIN_TOKEN_FILE          (optionnel) défaut /root/.garminconnect/garmin_tokens.json
    TOKEN_SYNC_INTERVAL        (optionnel) secondes entre deux vérifications, défaut 60

Aucune dépendance externe : uniquement la bibliothèque standard Python.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROW_ID = "default"
TABLE = "garmin_tokens"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
TOKEN_FILE = Path(
    os.environ.get("GARMIN_TOKEN_FILE", "/root/.garminconnect/garmin_tokens.json")
)
INTERVAL = int(os.environ.get("TOKEN_SYNC_INTERVAL", "60"))


def log(msg: str) -> None:
    print(f"[token_sync] {msg}", flush=True)


def _request(method: str, path: str, body: dict | None = None) -> list | None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY manquant")
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if method == "POST":
        # Upsert : insère la ligne, ou la remplace si elle existe déjà.
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}", data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def fetch_remote() -> str | None:
    rows = _request("GET", f"{TABLE}?id=eq.{ROW_ID}&select=content")
    return rows[0]["content"] if rows else None


def push_remote(content: str) -> None:
    _request(
        "POST",
        TABLE,
        {
            "id": ROW_ID,
            "content": content,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def write_local(content: str) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(content)
    TOKEN_FILE.chmod(0o600)


def pull() -> None:
    """Au démarrage : récupère les jetons les plus récents."""
    try:
        content = fetch_remote()
        if content:
            write_local(content)
            log(f"Jetons chargés depuis Supabase -> {TOKEN_FILE}")
            return
        log("Aucun jeton dans Supabase, passage au secours GARMIN_TOKENS_B64")
    except Exception as exc:  # Supabase injoignable : on ne bloque pas le démarrage
        log(f"Supabase injoignable ({exc}), passage au secours GARMIN_TOKENS_B64")

    b64 = os.environ.get("GARMIN_TOKENS_B64", "").strip()
    if b64:
        write_local(base64.b64decode(b64).decode())
        log(f"Jetons chargés depuis GARMIN_TOKENS_B64 -> {TOKEN_FILE}")
    else:
        log("ATTENTION : aucun jeton disponible")


def watch() -> None:
    """En arrière-plan : recopie dans Supabase chaque nouvelle version du fichier."""
    last_pushed: str | None = None
    try:
        remote = fetch_remote()
        last_pushed = sha(remote) if remote else None
    except Exception as exc:
        log(f"Lecture initiale Supabase impossible ({exc})")

    def check_and_push(reason: str) -> None:
        nonlocal last_pushed
        if not TOKEN_FILE.exists():
            return
        content = TOKEN_FILE.read_text()
        digest = sha(content)
        if digest == last_pushed:
            return
        try:
            push_remote(content)
            last_pushed = digest
            log(f"Jetons envoyés vers Supabase ({reason})")
        except Exception as exc:
            log(f"Échec de l'envoi vers Supabase ({exc}), nouvel essai plus tard")

    # Render envoie SIGTERM avant d'arrêter le conteneur : dernière sauvegarde.
    def on_term(signum, frame):
        check_and_push("arrêt du conteneur")
        sys.exit(0)

    signal.signal(signal.SIGTERM, on_term)

    check_and_push("démarrage")
    while True:
        time.sleep(INTERVAL)
        check_and_push("fichier modifié")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "pull":
        pull()
    elif command == "watch":
        watch()
    else:
        print(__doc__)
        sys.exit(1)
