"""Flow OAuth 2.0 Authorization Code pour l'API Whoop.

Securite :
- state CSRF compare strictement avant tout echange
- client_secret lu uniquement depuis os.environ, jamais hardcode, jamais logge
- redirection sur 127.0.0.1:3000 uniquement, ecoute une seule requete puis ferme
- aucun call sortant en dehors de api.prod.whoop.com
"""
from __future__ import annotations

import http.server
import os
import secrets
import sys
import time
import urllib.parse
import webbrowser
from typing import Optional

import httpx


AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
REDIRECT_URI = "http://localhost:3000/callback"
# offline est necessaire pour obtenir un refresh_token Whoop.
SCOPE = "offline read:recovery read:sleep read:workout read:cycles"


def _get_credentials() -> tuple[str, str]:
    """Lit client_id et client_secret depuis l'environnement. Leve si absent."""
    try:
        client_id = os.environ["WHOOP_CLIENT_ID"]
        client_secret = os.environ["WHOOP_CLIENT_SECRET"]
    except KeyError as e:
        raise RuntimeError(
            f"Variable d'environnement manquante : {e.args[0]}. "
            "Definis WHOOP_CLIENT_ID et WHOOP_CLIENT_SECRET."
        ) from e
    return client_id, client_secret


def _normalize_token_response(payload: dict) -> dict:
    """Convertit la reponse Whoop en dict normalise pour token_store.

    expires_in (secondes) -> expires_at (epoch UTC absolu).
    """
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload["refresh_token"],
        "expires_at": int(time.time()) + int(payload["expires_in"]),
    }


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handler one-shot pour le callback OAuth localhost.

    Stocke le code et le state recus dans des attributs de classe ; le serveur
    appelant lit ces attributs apres handle_request().
    """

    received_code: Optional[str] = None
    received_state: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self) -> None:  # noqa: N802 (interface imposee par stdlib)
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.startswith("/callback"):
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)
        _CallbackHandler.received_code = (params.get("code") or [None])[0]
        _CallbackHandler.received_state = (params.get("state") or [None])[0]
        _CallbackHandler.error = (params.get("error") or [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = (
            "<html><body><h2>Whoop MCP</h2>"
            "<p>Autorisation recue. Tu peux fermer cette fenetre.</p>"
            "</body></html>"
        )
        self.wfile.write(msg.encode("utf-8"))

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # silence total : on ne veut rien sur stdout/stderr
        return


def authorize_interactive() -> dict:
    """Lance le flow OAuth complet (browser + callback) et renvoie les tokens normalises."""
    client_id, _ = _get_credentials()
    state = secrets.token_urlsafe(16)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": state,
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    # reset des attributs de classe au cas ou un flow precedent aurait laisse des traces
    _CallbackHandler.received_code = None
    _CallbackHandler.received_state = None
    _CallbackHandler.error = None

    server = http.server.HTTPServer(("127.0.0.1", 3000), _CallbackHandler)
    try:
        print("[oauth] ouverture du navigateur pour autorisation Whoop", file=sys.stderr)
        webbrowser.open(auth_url)
        # handle_request() bloque jusqu'a la premiere requete puis rend la main
        server.handle_request()
    finally:
        server.server_close()

    if _CallbackHandler.error:
        raise RuntimeError(f"Whoop OAuth error: {_CallbackHandler.error}")
    if _CallbackHandler.received_code is None:
        raise RuntimeError("Aucun code recu du callback OAuth")
    # comparaison stricte du state pour bloquer le CSRF
    if _CallbackHandler.received_state != state:
        raise RuntimeError("State CSRF invalide dans le callback OAuth")

    return exchange_code(_CallbackHandler.received_code)


def exchange_code(code: str) -> dict:
    """Echange un authorization_code contre des tokens. Renvoie un dict normalise."""
    client_id, client_secret = _get_credentials()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    resp = httpx.post(TOKEN_URL, data=data, timeout=15.0)
    print(f"[oauth] POST /oauth/oauth2/token (exchange) -> {resp.status_code}", file=sys.stderr)
    resp.raise_for_status()
    return _normalize_token_response(resp.json())


def refresh_access_token(refresh_token: str) -> dict:
    """Rafraichit l'access_token.

    Whoop INVALIDE l'ancien refresh_token apres usage : le nouveau dict renvoye
    contient un nouveau refresh_token qui DOIT remplacer l'ancien dans le store.
    """
    client_id, client_secret = _get_credentials()
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": SCOPE,
    }
    resp = httpx.post(TOKEN_URL, data=data, timeout=15.0)
    print(f"[oauth] POST /oauth/oauth2/token (refresh) -> {resp.status_code}", file=sys.stderr)
    resp.raise_for_status()
    return _normalize_token_response(resp.json())
