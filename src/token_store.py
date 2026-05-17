"""Persistance locale des tokens OAuth Whoop sous %USERPROFILE%\\.whoop-mcp\\tokens.json.

Securite :
- on ne logge JAMAIS le contenu des tokens
- ACL Windows restrictive (icacls) appliquee a chaque ecriture : seul l'utilisateur courant peut lire
- pas de tiers, pas de cache memoire global
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


TOKEN_DIR: Path = Path(os.environ["USERPROFILE"]) / ".whoop-mcp"
TOKEN_PATH: Path = TOKEN_DIR / "tokens.json"


def _apply_windows_acl(path: Path) -> None:
    """Restreint l'acces au fichier au seul utilisateur courant via icacls.

    Equivalent Windows d'un chmod 600. On supprime l'heritage parent
    (/inheritance:r) puis on remplace toutes les ACL (/grant:r) par une
    seule entree donnant le controle total a l'utilisateur courant.
    """
    user = os.environ.get("USERNAME")
    if not user:
        raise RuntimeError("USERNAME environment variable not set; cannot apply ACL")

    # capture_output=True pour ne pas polluer stdout (qui sert au protocole MCP)
    result = subprocess.run(
        [
            "icacls",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"{user}:F",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # on logge le code de retour, jamais le path complet ni stderr
        # (stderr d'icacls ne contient pas de secret mais on reste prudent)
        print(f"[token_store] icacls returned {result.returncode}", file=sys.stderr)
        raise RuntimeError("Failed to apply restrictive ACL on tokens file")


def load_tokens() -> dict | None:
    """Charge les tokens depuis le disque. Renvoie None si le fichier n'existe pas.

    Le contenu n'est jamais logge.
    """
    if not TOKEN_PATH.exists():
        return None
    with TOKEN_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_tokens(tokens: dict) -> None:
    """Persiste les tokens et applique l'ACL restrictive.

    `tokens` doit contenir : access_token, refresh_token, expires_at (epoch UTC).
    """
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    # ecriture atomique : tmp puis remplacement
    tmp_path = TOKEN_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(tokens, f)
    tmp_path.replace(TOKEN_PATH)
    # on applique l'ACL apres le remplacement (sinon le replace casse l'ACL)
    _apply_windows_acl(TOKEN_PATH)


def is_expired(tokens: dict, skew: int = 60) -> bool:
    """Vrai si le token est expire (avec une marge de skew secondes par defaut)."""
    return time.time() + skew >= tokens.get("expires_at", 0)


def clear_tokens() -> None:
    """Supprime le fichier tokens pour forcer une reauthentification."""
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
