# Whoop MCP

Local MCP server that exposes your Whoop data (recovery, sleep, workouts, cycles) to Claude Desktop on Windows. Read-only, OAuth 2.0, tokens stored on disk protected by Windows ACLs, zero telemetry.

> Note: source code comments and docstrings are intentionally kept in French (security-review notes written by the author).

## Prerequisites

- Windows 10/11
- Python 3.10+
- An active Whoop account
- A Whoop Developer application (see below)

## 1. Create a Whoop Developer app

1. Go to https://developer.whoop.com and sign in
2. Create a new app
3. **Redirect URI**: `http://localhost:3000/callback` (exact, no trailing slash)
4. **Scopes to enable**:
   - `read:recovery`
   - `read:sleep`
   - `read:workout`
   - `read:cycles`
   - `offline` (required to obtain a refresh_token)
5. Note your `Client ID` and `Client Secret`

Do not enable `read:profile` or `read:body_measurement`: this server does not use them.

## 2. Installation

```powershell
# Replace <PATH> with the location where you cloned the repo
cd <PATH>\Whoop-MCP
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

For a **reproducible and auditable** install (exact pinned versions of the
~30 transitive dependencies), use the lock file instead:

```powershell
pip install -r requirements-lock.txt
```

## 3. Connect to Claude Desktop

Open `%APPDATA%\Claude\claude_desktop_config.json` (create it if it does not exist) and add the `whoop` section:

```json
{
  "mcpServers": {
    "whoop": {
      "command": "C:\\PATH\\TO\\Whoop-MCP\\venv\\Scripts\\python.exe",
      "args": ["C:\\PATH\\TO\\Whoop-MCP\\src\\server.py"],
      "env": {
        "WHOOP_CLIENT_ID": "your_client_id",
        "WHOOP_CLIENT_SECRET": "your_client_secret"
      }
    }
  }
}
```

Replace both placeholders with your real values.

Restart Claude Desktop.

## 4. First run

In Claude Desktop, type for example: *"Read my latest Whoop recovery"*.

On the first call, your browser opens the Whoop authorization page. You authorize the app. The local server on `localhost:3000` receives the code, exchanges it for tokens, and saves them to `%USERPROFILE%\.whoop-mcp\tokens.json` with restrictive Windows ACLs (only your user can read the file).

Subsequent calls use the stored tokens. When the access_token expires, the refresh_token is used automatically.

## Exposed tools

| Tool | Whoop endpoint | Data |
| --- | --- | --- |
| `get_recovery` | `GET /developer/v2/recovery` | HRV, RHR, recovery score |
| `get_sleep` | `GET /developer/v2/activity/sleep` | Stages, performance, duration |
| `get_workouts` | `GET /developer/v2/activity/workout` | Strain, average HR, sport |
| `get_cycles` | `GET /developer/v2/cycle` | Physiological cycle, strain |

All accept `start` and `end` (ISO 8601, optional) and `limit` (1-25, default 10).

## Reset authentication

To force a new authorization (revoked access, changed app, etc.):

```powershell
del "$env:USERPROFILE\.whoop-mcp\tokens.json"
```

The next call will restart the browser flow.

## Verify token ACLs

```powershell
icacls "$env:USERPROFILE\.whoop-mcp\tokens.json"
```

You should see only your Windows account (`<YOUR_USER>:(F)`) — no `BUILTIN\Users`, no `Everyone`.

## Verify imports without running the flow

```powershell
$env:WHOOP_CLIENT_ID="dummy"; $env:WHOOP_CLIENT_SECRET="dummy"
.\venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); import server; print('ok')"
```

## Security — points to review yourself

1. **Windows ACLs**: `src/token_store.py:_apply_windows_acl` runs `icacls /inheritance:r /grant:r <user>:F`. After the first auth, verify that `icacls tokens.json` shows only your user.
2. **CSRF state**: `src/oauth.py:authorize_interactive` compares `_CallbackHandler.received_state != state` before the exchange. Verify the comparison is strict and happens before the `exchange_code` call.
3. **No secret leaked in logs**: grepping `access_token\|refresh_token\|client_secret` in `src/` should only return internal manipulations, never an argument to `print` or an `f"..."` log.

## Architecture (4 files)

```
src/
  server.py        # MCP entrypoint, 4 tools
  whoop_client.py  # GET with refresh-on-401 and backoff on 429
  oauth.py         # browser flow + token exchange + refresh
  token_store.py   # load/save/clear + icacls ACL
```

No dependency other than `mcp` and `httpx` (pinned in `requirements.txt`). No outbound call outside `api.prod.whoop.com`.
