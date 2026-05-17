"""Client HTTP minimal pour l'API Whoop v2.

Securite :
- on ne logge que `METHOD path -> status`, jamais le body de reponse, jamais les tokens
- refresh automatique sur 401, une seule tentative pour eviter les boucles
- backoff exponentiel sur 429 (3 tentatives max)
- aucun call sortant en dehors de api.prod.whoop.com
"""
from __future__ import annotations

import sys
import time
from typing import Optional

import httpx

import oauth
import token_store


API_BASE = "https://api.prod.whoop.com/developer"
TIMEOUT = 15.0
MAX_429_RETRIES = 3


def _ensure_fresh_tokens() -> dict:
    """Charge les tokens du disque, lance le flow OAuth ou refresh si besoin."""
    tokens = token_store.load_tokens()
    if tokens is None:
        tokens = oauth.authorize_interactive()
        token_store.save_tokens(tokens)
        return tokens

    if token_store.is_expired(tokens):
        try:
            tokens = oauth.refresh_access_token(tokens["refresh_token"])
        except httpx.HTTPStatusError:
            # refresh casse : on force une reauth complete
            token_store.clear_tokens()
            tokens = oauth.authorize_interactive()
        token_store.save_tokens(tokens)
    return tokens


def _clamp_limit(limit: int) -> int:
    """Limite l'API Whoop : 1 <= limit <= 25, defaut 10."""
    if limit < 1:
        return 1
    if limit > 25:
        return 25
    return limit


def _build_params(
    start: Optional[str], end: Optional[str], limit: int
) -> dict:
    params: dict = {"limit": _clamp_limit(limit)}
    if start is not None:
        params["start"] = start
    if end is not None:
        params["end"] = end
    return params


def _get(path: str, params: dict) -> dict:
    """GET authentifie avec refresh-on-401 et retry-on-429.

    Le path est relatif a API_BASE (ex: "/v2/recovery").
    """
    tokens = _ensure_fresh_tokens()

    attempt = 0
    retried_after_refresh = False
    while True:
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        resp = httpx.get(API_BASE + path, params=params, headers=headers, timeout=TIMEOUT)
        # on ne logge JAMAIS resp.text ni headers d'autorisation
        print(f"[whoop_client] GET {path} -> {resp.status_code}", file=sys.stderr)

        if resp.status_code == 401 and not retried_after_refresh:
            # access_token rejete : tentative de refresh + une seule retry
            try:
                tokens = oauth.refresh_access_token(tokens["refresh_token"])
                token_store.save_tokens(tokens)
            except httpx.HTTPStatusError as e:
                token_store.clear_tokens()
                raise RuntimeError(
                    "Refresh OAuth echoue. Supprime %USERPROFILE%\\.whoop-mcp\\tokens.json "
                    "et relance pour reauthoriser."
                ) from e
            retried_after_refresh = True
            continue

        if resp.status_code == 429 and attempt < MAX_429_RETRIES:
            retry_after = resp.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                delay = int(retry_after)
            else:
                delay = 2**attempt  # 1, 2, 4
            time.sleep(delay)
            attempt += 1
            continue

        resp.raise_for_status()
        return resp.json()


def get_recovery(
    start: Optional[str] = None, end: Optional[str] = None, limit: int = 10
) -> dict:
    """GET /v2/recovery — collection des recoveries."""
    return _get("/v2/recovery", _build_params(start, end, limit))


def get_sleep(
    start: Optional[str] = None, end: Optional[str] = None, limit: int = 10
) -> dict:
    """GET /v2/activity/sleep — collection des sommeils."""
    return _get("/v2/activity/sleep", _build_params(start, end, limit))


def get_workouts(
    start: Optional[str] = None, end: Optional[str] = None, limit: int = 10
) -> dict:
    """GET /v2/activity/workout — collection des workouts."""
    return _get("/v2/activity/workout", _build_params(start, end, limit))


def get_cycles(
    start: Optional[str] = None, end: Optional[str] = None, limit: int = 10
) -> dict:
    """GET /v2/cycle — collection des cycles."""
    return _get("/v2/cycle", _build_params(start, end, limit))
