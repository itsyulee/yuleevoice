<div align="center">

**🌐 English (current)** &nbsp;·&nbsp; [**🇻🇳 Tiếng Việt →**](docs/README_VN.md)

<h1>Discord Multi-Token Voice 24/7 &amp; Web Dashboard</h1>

**Run dozens — or hundreds — of Discord accounts in voice channels, 24/7, from a modern real-time web dashboard or an interactive terminal CLI.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![discord.py-self](https://img.shields.io/badge/discord.py--self-2.0-5865F2?logo=discord&logoColor=white)](https://github.com/dolfies/discord.py-self)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen)](#roadmap)
[![License](https://img.shields.io/badge/License-Not%20specified-lightgrey)](#license-and-credits)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows%20%7C%20macOS-0f172a)](#installation)

<a href="#overview">Overview</a> ·
<a href="#key-features">Features</a> ·
<a href="#web-dashboard">Dashboard</a> ·
<a href="#installation">Installation</a> ·
<a href="#configuration">Configuration</a> ·
<a href="#architecture">Architecture</a> ·
<a href="#terminal-cli">Terminal CLI</a> ·
<a href="#token-tools">Token Tools</a> ·
<a href="#rest-api-reference">REST API</a> ·
<a href="#security-and-privacy">Security</a> ·
<a href="#troubleshooting">Troubleshooting</a>

<br><br>

<img src="docs/fig.png" alt="Discord Multi-Token Voice Web Dashboard" width="100%">

</div>

---

> [!WARNING]
> **Discord Terms of Service.** This project automates Discord **user accounts** (self-bot behavior). Automating user accounts violates Discord's Terms of Service and can result in **account termination**. Use it only on accounts you fully control and only if you accept the risk.
>
> **Token privacy.** `tokens.txt`, `.env`, and every `*.txt` export contain account credentials. Never commit them, never paste them into screenshots or logs, and never share the Cloudflare tunnel URL together with your dashboard password. `.gitignore` already excludes these files — keep it that way.

## Overview

**Discord Multi-Token Voice 24/7** is a multi-account voice manager built on `discord.py-self`. It keeps an arbitrary number of user tokens connected to voice/stage channels around the clock, and gives you two ways to drive them:

| Interface | Entry point | Description |
| :--- | :--- | :--- |
| **Web Dashboard** | `dashboard.py` (`core/web.py`, `core/api.py`) | Dark-themed single-page app served by FastAPI with a real-time WebSocket channel, bilingual EN/VI UI, per-bot controls, live logs, token manager, and an optional secure Cloudflare public URL. |
| **Terminal CLI** | `self-bot.py` | The original interactive console: mode selection, login pacing, and a control menu for bulk mic / camera / deafen / reaction / rename actions. |

Both interfaces share the same engine (`core/engine.py`), the same configuration (`config.py` + `.env`), and the same `tokens.txt` file, so you can switch between them at any time.

> [!NOTE]
> The web dashboard is **push-based**: bot health, latency, voice state and the log console stream over a WebSocket connection that auto-reconnects every 3 seconds. Switching language (EN ⇄ VI) is instant and never reloads the page.

## Key Features

### Voice Automation

- **Normal Mode** — supply one or more voice channel IDs; tokens are distributed evenly across the channels in round-robin order.
- **Auto-Room Mode** — a configurable number of *leader* tokens join a lobby channel; when a server bot moves them into generated rooms, the remaining tokens are distributed across every detected room.
- **24/7 persistence** — bots hold their voice session, report gateway latency, and surface connection errors in real time.

### Modern Web Dashboard (`dashboard.py`, `core/web.py`)

- **Real-time WebSocket streaming** (`/ws`) of bot health, latency, voice states, stream state, and a live log console.
- **Zero external dependencies** — all HTML, CSS, JavaScript and SVG icons are inlined; no CDN, no build step, no framework.
- **Bilingual UI** — instant English / Tiếng Việt toggle with **119 keys per language** (100% key parity), persisted in `localStorage`.
- **Global and per-bot controls** — mute, deafen, camera, Go-Live stream simulation, move channel, individual chat.
- **Discord Message Reaction Panel** — snowflake validation (17–20 digits), dual-mode emoji selector (built-in 24-emoji grid + custom `:name:` / `name:id` input), live preview, spinner loading state and status toasts.
- **Chat Single & Chat All** — send a message from one account, or from every ready account with a configurable delay (default 1.0 s, step 0.1 s).
- **Built-in Token Manager** — inspect masked/full tokens, edit and save them with an automatic `.bak` backup before every write.
- **Cloudflare Tunnel Integration** (`core/tunnel.py`) — automatically starts `cloudflared` and exposes a secure public URL for remote access, with a one-click copy button.

### Token Utilities (`Token Tools/`)

- `get_token.py` — browser-assisted login and token extractor (also writes account info reports).
- `check_info_token.py` — batch token validation and account status checker.
- `browser_login.py` — one-click login tester powered by `undetected-chromedriver`.

### Interface Matrix

| Capability | Web Dashboard | Terminal CLI |
| :--- | :---: | :---: |
| Real-time state & logs | ✅ WebSocket push | ⚠️ Text logs only |
| Language support | ✅ EN / VI toggle | ⚠️ Vietnamese console |
| Authentication | ✅ Password + JWT | ❌ Local terminal only |
| Remote access | ✅ Cloudflare tunnel | ⚠️ SSH |
| Normal / Auto-Room modes | ✅ | ✅ |
| Bulk mute / deaf / cam / stream | ✅ 8 actions | ⚠️ Menu toggles |
| Per-bot mic / deaf / cam / stream | ✅ | ❌ |
| Move a specific bot | ✅ Channel picker modal | ❌ |
| Individual chat | ✅ Per-bot modal | ❌ |
| Chat all / spam chat | ✅ With delay | ❌ |
| Message reactions | ✅ Emoji grid + custom | ✅ Prompt-based |
| Token manager | ✅ View / edit / save | ❌ Manual file edit |
| Rename (single / all) | ✅ | ✅ Rename all |

## Web Dashboard

<p align="center">
  <img src="docs/fig.png" alt="Discord Multi-Token Voice Web Dashboard" width="100%">
</p>

```
GET /            →   Single-page dashboard (inline HTML/CSS/JS)
GET /ws          →   Authenticated realtime channel (state_update · log · tunnel_status)
```

### Layout

1. **Login screen** — minimalist password card with show/hide toggle and EN/VI switcher. The JWT is stored in `localStorage` and re-used on reload (auto-login).
2. **Header** — brand, mode + uptime pills, **Tokens** pill (total token count), Cloudflare tunnel URL with copy button, language switch, logout.
3. **Stat cards** — Total Bots · Online · In Voice · Errors (live).
4. **Bots grid** — one card per account with avatar, name, status badge (`VOICE` / `READY` / `ERROR` / `CONNECTING`), ping, channel and guild, plus per-bot controls: **Mic · Deaf · Cam · Stream · Move · Chat**.
5. **Controls panel** — mode selector, channel IDs, delay, leader count, `START` / `STOP`, eight bulk actions, rename-all.
6. **Chat All panel** — text channel ID (remembered in `localStorage`), message, delay, “Send to All”.
7. **Message Reaction panel** — channel ID, message ID, emoji grid / custom input, preview, “Send Reaction”.
8. **Live Log Console** — 300 px auto-scrolling console with level colors (`INFO` / `WARNING` / `ERROR` / `DEBUG`) and a clear button.
9. **Token Manager** — collapsible editor for `tokens.txt`.

### Keyboard Shortcuts

| Keys | Action |
| :--- | :--- |
| <kbd>Enter</kbd> | Submit the dashboard password on the login screen |
| <kbd>Esc</kbd> | Close the confirm dialog, the channel picker, the chat modal, or the emoji picker |
| <kbd>Ctrl</kbd> + <kbd>Enter</kbd> (or <kbd>⌘</kbd> + <kbd>Enter</kbd>) | Send a message from the individual chat modal |
| <kbd>Ctrl</kbd> + <kbd>C</kbd> | Stop the dashboard server (graceful shutdown: all bots and the tunnel are closed) |

### Behaviour Notes

- Bulk actions and destructive operations (`STOP`, `Save Tokens`, `Rename All`) ask for confirmation first.
- Every API call attaches `Authorization: Bearer <JWT>`; an expired token triggers an automatic logout back to the login screen.
- The WebSocket client retries every 3 seconds while the tab stays open.

## Installation

> [!IMPORTANT]
> - **Python 3.10+** is required (3.11/3.12 recommended; the reference environment runs 3.12).
> - The **first launch asks for a dashboard password** in the terminal and writes `.env` for you. This prompt needs an interactive terminal — on headless servers create `.env` manually (see [Configuration](#configuration)).
> - Cloudflare Tunnel is enabled by default (`ENABLE_TUNNEL=true`) and requires `cloudflared` — see the [Cloudflare tip](#remote-access-with-cloudflare-tunnel).

### Prerequisites

| Requirement | Notes |
| :--- | :--- |
| Python 3.10+ | `python3 --version` |
| pip | Usually bundled with Python |
| Git | To clone the repository |
| `cloudflared` *(optional)* | Only for remote tunnel access |
| Google Chrome *(optional)* | Only for `Token Tools/` |

### Quick Start

**Windows**

```bat
run.bat
```

`run.bat` creates the `.venv` virtual environment if needed, installs `requirements.txt`, and launches the dashboard.

**Linux / macOS**

```bash
chmod +x run.sh
./run.sh
```

> [!TIP]
> **Running on a headless VPS.** Start the launcher inside `tmux` or `screen` so the dashboard survives SSH disconnects:
> ```bash
> tmux new -s dashboard
> ./run.sh
> # detach with Ctrl+B, then D — re-attach with: tmux attach -t dashboard
> ```

### Manual Setup

```bash
# 1. Clone
git clone https://github.com/kwishtt/Discord-Multi-Voice.git
cd Discord-Multi-Voice

# 2. Create the virtual environment
python3 -m venv .venv

# 3. Activate it
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate.bat       # Windows

# 4. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 5. Add your tokens (one per line, no quotes)
#    tokens.txt

# 6. Launch the dashboard
python dashboard.py
```

The terminal prints the banner plus both access URLs:

```text
 Dashboard đang chạy!

 Truy cập LAN   : http://192.168.1.20:8080
 Truy cập Remote: https://random-words-here.trycloudflare.com

 Bấm Ctrl+C để dừng hệ thống.
```

## Configuration

### Environment Variables (`.env`)

A `.env.example` file documents every supported variable. On first run the dashboard prompts for the password and creates `.env` automatically.

| Variable | Default | Description |
| :--- | :--- | :--- |
| `HOST` | `0.0.0.0` | Interface the dashboard binds to |
| `PORT` | `8080` | Dashboard port |
| `DASHBOARD_PASSWORD` | *(prompted)* | Password required to log in |
| `JWT_SECRET` | *(auto-generated)* | HS256 signing key (`secrets.token_hex(32)`) |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_HOURS` | `72` | Session lifetime in hours |
| `TOKENS_FILE` | `tokens.txt` | Token file location (relative paths resolve to the project root) |
| `ENABLE_TUNNEL` | `true` | Start a Cloudflare quick tunnel on boot |
| `CLOUDFLARED_PATH` | `/usr/local/bin/cloudflared` | Path to the `cloudflared` binary (falls back to `PATH`) |

First-run prompt:

```text
Đặt mật khẩu dashboard: █
```

> [!IMPORTANT]
> The dashboard never stores your password — only its JWT secret is saved. Treat `.env` as a credential file: it is already listed in `.gitignore`.

### Token File Format

`tokens.txt` contains **one token per line**, no quotes, no comments:

```text
MTIzNDU2Nzg5MDEyMzQ1Njc4OTAuQUJDREVGLmFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6
MTIzNDU2Nzg5MDEyMzQ1Njc4OTAuQUJDREVGLnp6enp6enp6enp6enp6enp6enp6enp6enp6
```

Rules:

- One token per line; blank lines are ignored.
- Tokens shorter than 5 characters are skipped by the engine.
- Saving from the dashboard writes the file atomically and keeps the previous content in `tokens.txt.bak`.
- `TOKENS_FILE` may point anywhere; relative paths are anchored to the project directory, so the dashboard behaves the same no matter which folder you launch it from.

## Architecture

```text
Browser (SPA, EN/VI, Vanilla JS)
   │  REST + WebSocket  (JWT)
   ▼
FastAPI  (core/api.py · core/web.py · core/auth.py)
   │
   ├── core/engine.py      Bot / BotManager  ──►  discord.py-self clients ──► Discord Gateway & Voice
   ├── core/logger.py      WebSocketLogHandler (buffered logs → dashboard)
   └── core/tunnel.py      CloudflareTunnelManager ──► cloudflared quick tunnel
```

<details>
<summary><strong>Project tree (click to expand)</strong></summary>

```text
Discord_Voice/
├── README.md                     # This documentation (English)
├── config.py                     # Typed configuration loader + first-run setup (.env)
├── dashboard.py                  # Web dashboard entrypoint (FastAPI + uvicorn + banner)
├── self-bot.py                   # Terminal CLI (legacy interface, unchanged)
├── run.sh                        # Linux / macOS launcher (creates .venv, installs, runs)
├── run.bat                       # Windows launcher
├── requirements.txt              # Python dependencies
├── .env.example                  # Documented environment template
├── tokens.txt                    # Your Discord tokens (one per line — gitignored)
├── tokens.txt.bak                # Automatic backup written before every save
├── dead_tokens.txt               # Tokens reported invalid by the checker tool
├── token_details.csv             # Account details exported by the checker tool
├── evs.txt / user_info.txt       # Outputs of the token extractor tool
├── core/
│   ├── __init__.py
│   ├── api.py                    # REST router (/api/*)
│   ├── auth.py                   # JWT create/verify + HTTP auth middleware
│   ├── engine.py                 # Bot + BotManager (voice, toggles, chat, reactions, stream)
│   ├── logger.py                 # WebSocket log handler + app logger
│   ├── tunnel.py                 # Cloudflare quick-tunnel manager
│   └── web.py                    # Single-page dashboard + /ws endpoint
├── Token Tools/
│   ├── get_token.py              # Browser login → token extractor
│   ├── check_info_token.py       # Batch token validity checker
│   └── browser_login.py          # One-click login tester
└── docs/
    ├── README_VN.md              # Vietnamese documentation (this document's translation)
    └── GUIDE_VN.md               # 24/7 VPS deployment guide (Vietnamese)
```

</details>

<details>
<summary><strong>Core modules (click to expand)</strong></summary>

| Module | Responsibilities |
| :--- | :--- |
| `config.py` | Loads `.env` via `python-dotenv`, exposes a typed `AppConfig` singleton, prompts for the dashboard password on first run, generates `JWT_SECRET`. |
| `core/engine.py` | `Bot` (one per token): join voice, toggle mic/deaf/cam, stream simulation (gateway op 18/19), rename, send messages, unique `bot_id`, latency/uptime/state serialization. `BotManager`: token I/O, Normal & Auto-Room start modes, bulk + single toggles, move, chat, reactions, rename, summary, state listeners. |
| `core/api.py` | FastAPI router with all REST endpoints, Pydantic request models, 400/401 handling. |
| `core/auth.py` | `create_token` / `verify_token` (PyJWT, HS256) and `auth_middleware` protecting every route except `/`, `/api/login`, `/favicon.ico`. |
| `core/logger.py` | Buffered root-logger handler (500 entries) that streams log records to WebSocket listeners from any thread. |
| `core/tunnel.py` | Runs `cloudflared tunnel --url http://127.0.0.1:<port>`, parses the `trycloudflare.com` URL with a 25 s timeout, drains output, and cleans up the process group on stop. |
| `core/web.py` | Serves the inline SPA and the authenticated `/ws` channel (auth handshake → `state_update` + `logs_history` + `tunnel_status` → live stream). |

</details>

## Terminal CLI

`self-bot.py` remains available as the original terminal interface and is **not modified** by the web dashboard work. It is useful for quick local sessions or when you prefer the console.

```bash
python self-bot.py
```

| Step | What happens |
| :--- | :--- |
| 1 | Select mode: `1` Normal (channel IDs) or `2` Auto-Room (lobby + leaders). |
| 2 | Choose login pacing: *Turbo* (<kbd>y</kbd>, 3 s delay) or *Safe* (<kbd>Enter</kbd>, 8 s delay). |
| 3 | Bots log in and join voice; a control menu appears. |

Menu actions: toggle mic (`1`), camera (`2`), deafen (`3`), spam reaction (`4`), rename all (`5`), exit (`6`).

<details>
<summary><strong>Owner echo command (click to expand)</strong></summary>

Accounts whose Discord user ID matches the configured `OWNER_ID` constant can make every bot echo a message by sending a chat message in this format:

```text
<!your message here>
```

Each bot waits a randomized 0.5–2.5 s before sending, which avoids clustering all sends in the same instant. Configure the owner ID directly in `self-bot.py` (`OWNER_ID`) and in `core/engine.py` for the dashboard's engine.

</details>

> [!NOTE]
> The terminal CLI has no authentication layer — it can only be operated by someone with shell access to the machine. For remote access, use the web dashboard with its JWT login and (optionally) the Cloudflare tunnel.

## Token Tools

<details>
<summary><strong><code>Token Tools/get_token.py</code> — browser login &amp; token extractor (click to expand)</strong></summary>

Opens Discord in a real Chrome window (via `undetected-chromedriver`), waits for you to log in manually, extracts the token from the browser session, then appends output files:

- `tokens.txt` — the token itself (one per line).
- `evs.txt` — `email:username:user_id:token`.
- `user_info.txt` — a formatted report (ID, username, e-mail, phone, MFA, verified, Nitro, token).

> [!TIP]
> Run these tools **from the repository root** (`python "Token Tools/get_token.py"`) so the output files land next to the dashboard's `tokens.txt`.

</details>

<details>
<summary><strong><code>Token Tools/check_info_token.py</code> — batch validity checker (click to expand)</strong></summary>

Reads every token from `tokens.txt`, queries `GET /users/@me` concurrently, then rewrites the results:

- `tokens.bak` — raw backup of the input list.
- `tokens.txt` — only the **valid** tokens (deduplicated).
- `dead_tokens.txt` — invalid tokens for review.
- `token_details.csv` — `Token, Username, Email, Phone, Verified` for every valid account.

Run it whenever bots fail to log in — expired or revoked tokens are the most common cause.

</details>

<details>
<summary><strong><code>Token Tools/browser_login.py</code> — login tester (click to expand)</strong></summary>

A minimal script that launches an undetected Chrome session to confirm that a token can still authenticate and reach the Discord web client. Useful for verifying accounts before pushing them to a large fleet.

</details>

## REST API Reference

All endpoints are mounted under `/api`. Except for `POST /api/login`, every request must send `Authorization: Bearer <JWT>`; missing or invalid tokens receive `401 {"error": "Unauthorized"}`.

| Method | Endpoint | Body / Query | Response |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/login` | `{"password": "..."}` | `{"token", "expires_in"}` · `401 {"error":"Sai mật khẩu"}` |
| `GET` | `/api/status` | — | Bot summary merged with tunnel status |
| `POST` | `/api/start` | `{"mode": "normal"\|"auto_room", "channel_ids": ["..."], "delay": 5, "leader_count": 5}` | `{"success", "message"}` (runs in background) |
| `POST` | `/api/stop` | — | `{"success", "message"}` |
| `POST` | `/api/toggle` | `{"bot_id"?, "mute"?, "deaf"?, "video"?, "stream"?}` | `{"success", "affected"}` |
| `POST` | `/api/rename` | `{"bot_id"?, "name": "..."}` | `{"success", "affected"}` |
| `POST` | `/api/move` | `{"target_channel_id": "...", "bot_ids"?: ["..."]}` | `{"success", "moved"}` |
| `POST` | `/api/reaction` | `{"channel_id", "message_id", "emoji"}` | `{"success", "reacted"}` |
| `POST` | `/api/chat/single` | `{"bot_id", "channel_id", "message"}` | `{"success", "sent": 0\|1}` |
| `POST` | `/api/chat/all` | `{"channel_id", "message", "delay": 1.0}` | `{"success", "sent": N}` |
| `GET` | `/api/bots/{bot_id}/voice-channels` | — | `{"channels": [{"id","name","guild_name","user_limit","member_count"}]}` |
| `GET` | `/api/tokens` | — | `{"count", "tokens": [{"index","masked","full"}]}` |
| `PUT` | `/api/tokens` | `{"tokens": ["..."]}` | `{"success", "count"}` |
| `GET` | `/api/logs` | — | `{"logs": [...]}` |
| `DELETE` | `/api/logs` | — | `{"success"}` |

**Bot identifiers** — `bot_id` is the Discord user ID (`str(user.id)`) once the account is logged in, and a stable `tok-<sha256-prefix>` otherwise. Both the API and the dashboard UI use this value, so per-bot actions always target exactly the intended account, even when tokens share a prefix.

<details>
<summary><strong>WebSocket protocol (<code>/ws</code>) — click to expand</strong></summary>

1. Client connects and sends `{"type": "auth", "token": "<JWT>"}` within 10 seconds.
2. Invalid or missing token → `{"type": "error", "message": "Unauthorized"}` and the connection closes.
3. On success the server pushes, in order:
   - `{"type": "state_update", "data": { ... }}`
   - `{"type": "logs_history", "data": [ ... ]}`
   - `{"type": "tunnel_status", "data": { ... }}`
4. Afterwards the connection streams live `state_update` and `log` messages. Listeners are removed automatically on disconnect.

```bash
# Quick check with curl (REST)
curl -s http://127.0.0.1:8080/api/login \
  -H 'Content-Type: application/json' \
  -d '{"password":"your-dashboard-password"}'
```

</details>

## Security and Privacy

> [!WARNING]
> - **Discord accounts can be banned** for self-bot automation. This is inherent to the project's design, not a bug.
> - Treat tokens like passwords: anyone holding a token owns the account until the session is revoked.
> - The Cloudflare tunnel publishes your dashboard to the public internet — always keep a strong `DASHBOARD_PASSWORD` while the tunnel is enabled.

Practical hardening checklist:

- [x] `.env`, `tokens.txt` and every `*.txt` export are excluded by `.gitignore`.
- [x] Dashboard sessions are JWT-signed (HS256) and expire after `JWT_EXPIRE_HOURS` (default 72 h).
- [x] Token saves keep a `.bak` copy of the previous file.
- [ ] Rotate `JWT_SECRET` after sharing a tunnel URL with anyone.
- [ ] Disable the tunnel (`ENABLE_TUNNEL=false`) when you only need LAN access.

## Troubleshooting

<details>
<summary><strong>The first-run password prompt never appears (headless / systemd / CI)</strong></summary>

`first_run_setup()` uses `getpass`, which needs an interactive terminal. Create `.env` manually before launching:

```bash
cp .env.example .env
# then edit: DASHBOARD_PASSWORD and JWT_SECRET
```

Generate a secret with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

</details>

<details>
<summary><strong>“Không tìm thấy file token” / tokens are not loading</strong></summary>

- Ensure `tokens.txt` exists next to `dashboard.py` (or point `TOKENS_FILE` at the right file).
- Check the format: **one token per line**, no quotes, no commas.
- Use `Token Tools/check_info_token.py` to detect revoked tokens.
- The dashboard loads tokens from disk on every startup and re-reads the file each time the Token Manager is expanded.

</details>

<details>
<summary><strong>“Cloudflare Tunnel không khả dụng”</strong></summary>

- Install `cloudflared` (e.g. `sudo dnf install cloudflared` or download from Cloudflare).
- Update `CLOUDFLARED_PATH` in `.env` if the binary is not at `/usr/local/bin/cloudflared`.
- The manager also falls back to `shutil.which("cloudflared")`, and waits up to 25 s for the public URL. If your network blocks Cloudflare, disable the tunnel with `ENABLE_TUNNEL=false`.

</details>

<details>
<summary><strong>Port 8080 already in use</strong></summary>

Change `PORT` in `.env` (for example `PORT=8090`) and restart. On Linux you can identify the current owner with `ss -ltnp | grep 8080`.

</details>

<details>
<summary><strong>Dashboard asks me to log in again / 401 everywhere</strong></summary>

Sessions expire after `JWT_EXPIRE_HOURS` (72 h by default). Log in again, or increase the value in `.env`. If it happens immediately, verify that `JWT_SECRET` is not empty and that the browser clock is correct.

</details>

<details>
<summary><strong>Reaction / chat / move actions fail</strong></summary>

- Channel and message IDs must be **snowflakes** (17–20 digits).
- Custom reactions require the `name:id` form (for example `pepe:123456789012345678`); `:pepe:` shorthand is accepted as input but needs the numeric ID to be sent to Discord.
- The account must still be a member of the guild and must have permission to use the channel.
- Move requires the bot to be logged in; the channel picker lists every voice/stage channel across the bot's guilds.

</details>

<details>
<summary><strong>Bots do not join voice / stay silent</strong></summary>

- Confirm the channel IDs belong to the same guild as the tokens.
- Start with a small batch first: Discord rate-limits aggressive login bursts.
- Watch the log console for `Token không hợp lệ`, permission errors, or `Channel ID ... not found`.

</details>

<details>
<summary><strong>Cannot open the dashboard from another device</strong></summary>

- Keep `HOST=0.0.0.0` and allow the port through your firewall (`firewalld`, `ufw`, or the VPS provider's security group).
- Use the **LAN** URL printed at startup, or enable the tunnel for access from anywhere.

</details>

<details>
<summary><strong><code>./run.sh: Permission denied</code></strong></summary>

```bash
chmod +x run.sh
./run.sh
```

</details>

## Roadmap

Completed:

- [x] Typed configuration loader with first-run `.env` bootstrap
- [x] `Bot` / `BotManager` engine with Normal and Auto-Room modes
- [x] REST API with JWT authentication and middleware
- [x] Real-time WebSocket dashboard (state, logs, tunnel status)
- [x] Bilingual UI — 119 keys per language, instant switching
- [x] Per-bot and bulk voice controls (mic, deaf, cam, stream)
- [x] Move-to-channel picker, individual chat, chat-all with delay
- [x] Message Reaction panel with emoji grid and snowflake validation
- [x] Built-in Token Manager with automatic backups
- [x] Cloudflare quick-tunnel integration
- [x] Terminal CLI preserved alongside the dashboard

Under consideration:

- [ ] Docker Compose deployment for one-command VPS setup
- [ ] Automatic token health monitoring with scheduled checks
- [ ] Per-bot latency and uptime charts in the dashboard
- [ ] Role-based accounts for multi-operator dashboards

## License and Credits

No `LICENSE` file is currently included in this repository. Unless a license is added, all rights are reserved by the author — contact the maintainer before redistributing or reusing this code.

- **Author / maintainer:** [kwishtt](https://github.com/kwishtt)
- **Repository:** [github.com/kwishtt/Discord-Multi-Voice](https://github.com/kwishtt/Discord-Multi-Voice/tree/main)
- **Built with:** [discord.py-self](https://github.com/dolfies/discord.py-self), [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), [PyJWT](https://pyjwt.readthedocs.io/), [python-dotenv](https://github.com/theskumar/python-dotenv), [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/)

<div align="center">

**[⬆ Back to top](#overview)** · [🇻🇳 Đọc bản tiếng Việt](docs/README_VN.md)

<sub>Use responsibly — you are solely responsible for how you use this software and for the accounts you automate.</sub>

</div>
