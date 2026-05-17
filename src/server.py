"""Entrypoint du serveur MCP Whoop.

Expose 4 outils en lecture seule a Claude Desktop : get_recovery, get_sleep,
get_workouts, get_cycles. Chaque outil prend start/end (ISO 8601, optionnels)
et limit (1-25, defaut 10).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# `python src/server.py` ne met pas src/ dans sys.path par defaut, on l'ajoute
# pour que les imports absolus `import oauth` etc. fonctionnent.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

import whoop_client  # noqa: E402


def _check_credentials() -> None:
    """Verifie au demarrage que les credentials OAuth sont definis."""
    missing = [
        v for v in ("WHOOP_CLIENT_ID", "WHOOP_CLIENT_SECRET") if not os.environ.get(v)
    ]
    if missing:
        print(
            f"[server] Variable(s) d'environnement manquante(s) : {', '.join(missing)}. "
            "Definis-les dans claude_desktop_config.json (champ env).",
            file=sys.stderr,
        )
        sys.exit(1)


_check_credentials()

mcp = FastMCP("whoop")


@mcp.tool()
def get_recovery(
    start: str | None = None, end: str | None = None, limit: int = 10
) -> dict:
    """Recupere les donnees de recovery Whoop (HRV, RHR, score).

    Args:
        start: borne inferieure ISO 8601 (ex: "2026-05-01T00:00:00Z"). Optionnel.
        end: borne superieure ISO 8601. Optionnel.
        limit: nombre d'entrees (1-25, defaut 10).
    """
    return whoop_client.get_recovery(start, end, limit)


@mcp.tool()
def get_sleep(
    start: str | None = None, end: str | None = None, limit: int = 10
) -> dict:
    """Recupere les donnees de sommeil Whoop (stages, performance, duree).

    Args:
        start: borne inferieure ISO 8601. Optionnel.
        end: borne superieure ISO 8601. Optionnel.
        limit: nombre d'entrees (1-25, defaut 10).
    """
    return whoop_client.get_sleep(start, end, limit)


@mcp.tool()
def get_workouts(
    start: str | None = None, end: str | None = None, limit: int = 10
) -> dict:
    """Recupere les workouts Whoop (strain, HR moyenne, sport).

    Args:
        start: borne inferieure ISO 8601. Optionnel.
        end: borne superieure ISO 8601. Optionnel.
        limit: nombre d'entrees (1-25, defaut 10).
    """
    return whoop_client.get_workouts(start, end, limit)


@mcp.tool()
def get_cycles(
    start: str | None = None, end: str | None = None, limit: int = 10
) -> dict:
    """Recupere les cycles Whoop (jour, strain, HR moyenne).

    Args:
        start: borne inferieure ISO 8601. Optionnel.
        end: borne superieure ISO 8601. Optionnel.
        limit: nombre d'entrees (1-25, defaut 10).
    """
    return whoop_client.get_cycles(start, end, limit)


if __name__ == "__main__":
    mcp.run()
