"""Phục vụ HTML dashboard và WebSocket realtime."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from core.auth import verify_token
from core.engine import bot_manager
from core.logger import app_logger, log_handler
from core.tunnel import tunnel_manager

router: APIRouter = APIRouter()

AUTH_TIMEOUT_SECONDS = 10.0
MESSAGE_QUEUE_SIZE = 1000


# -----------------------------------------------------------------------------
# WebSocket
# -----------------------------------------------------------------------------
async def _reject(websocket: WebSocket) -> None:
    """Gửi lỗi Unauthorized rồi đóng kết nối."""
    with contextlib.suppress(Exception):
        await websocket.send_json({"type": "error", "message": "Unauthorized"})
    with contextlib.suppress(Exception):
        await websocket.close(code=1008)


def _enqueue(queue: asyncio.Queue[dict[str, Any]], message: dict[str, Any]) -> None:
    """Thêm message vào queue, bỏ qua nếu queue đầy."""
    try:
        queue.put_nowait(message)
    except asyncio.QueueFull:
        app_logger.debug("Queue WebSocket đầy; bỏ qua %s", message.get("type"))


async def _writer_loop(
    websocket: WebSocket, queue: asyncio.Queue[dict[str, Any]]
) -> None:
    """Gửi message từ queue tới client theo đúng thứ tự."""
    while True:
        message = await queue.get()
        try:
            await websocket.send_json(message)
        except Exception:
            return


async def _stream_events(websocket: WebSocket) -> None:
    """Đăng ký listener và đẩy state/log realtime cho tới khi client ngắt."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=MESSAGE_QUEUE_SIZE)

    async def on_state(_state: dict[str, Any]) -> None:
        _enqueue(queue, {"type": "state_update", "data": bot_manager.get_summary()})

    async def on_log(entry: dict[str, str]) -> None:
        _enqueue(queue, {"type": "log", "data": entry})

    bot_manager.add_state_listener(on_state)
    log_handler.add_listener(on_log)
    writer_task = asyncio.create_task(_writer_loop(websocket, queue))

    try:
        await websocket.send_json(
            {"type": "state_update", "data": bot_manager.get_summary()}
        )
        await websocket.send_json(
            {"type": "logs_history", "data": log_handler.get_recent_logs()}
        )
        await websocket.send_json(
            {"type": "tunnel_status", "data": tunnel_manager.get_status()}
        )

        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        app_logger.warning("WebSocket session kết thúc: %s", exc)
    finally:
        writer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await writer_task
        bot_manager.remove_state_listener(on_state)
        log_handler.remove_listener(on_log)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Xác thực JWT qua message đầu tiên rồi mở luồng realtime."""
    await websocket.accept()

    try:
        raw = await asyncio.wait_for(
            websocket.receive_json(), timeout=AUTH_TIMEOUT_SECONDS
        )
    except WebSocketDisconnect:
        return
    except (asyncio.TimeoutError, ValueError, json.JSONDecodeError):
        await _reject(websocket)
        return

    token = (
        raw.get("token")
        if isinstance(raw, dict) and raw.get("type") == "auth"
        else None
    )
    if not isinstance(token, str) or verify_token(token) is None:
        await _reject(websocket)
        return

    # Handler log cần event loop để đẩy log từ mọi thread tới dashboard
    log_handler.set_loop(asyncio.get_running_loop())
    app_logger.info("Dashboard kết nối WebSocket.")
    await _stream_events(websocket)


# -----------------------------------------------------------------------------
# Dashboard HTML
# -----------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """Trả toàn bộ HTML dashboard dưới dạng single-page app."""
    return HTMLResponse(content=get_dashboard_html())


# Alias để dashboard.py đăng ký route trực tiếp
dashboard_route = dashboard


def get_dashboard_html() -> str:
    """Trả HTML/CSS/JS inline của dashboard (không phụ thuộc bên ngoài)."""
    return _DASHBOARD_HTML


_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>kwishtt</title>
<style>
:root{
  --bg:#1e1f22; --surface:#2b2d31; --surface-2:#313338; --surface-3:#383a40;
  --border:#3f4147; --border-strong:#4e5058;
  --text:#f2f3f5; --text-muted:#b5bac1; --text-faint:#949ba4;
  --accent:#5865f2; --accent-hover:#4752c4; --accent-soft:rgba(88,101,242,.16);
  --green:#23a55a; --yellow:#f0b232; --red:#f23f43; --gray:#80848e;
  --radius:10px; --radius-lg:14px;
  --shadow:0 12px 32px rgba(0,0,0,.5);
  --mono:"Cascadia Code","Fira Code",Consolas,"Courier New",monospace;
}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:14px;line-height:1.5;}
.hidden{display:none !important;}
.mono{font-family:var(--mono);}
h2{margin:0;font-size:15px;font-weight:600;}
h3{margin:0 0 8px;font-size:16px;}
a{color:var(--accent);}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px;}
::selection{background:var(--accent-soft);}
@media (prefers-reduced-motion:reduce){
  *{transition:none !important;animation:none !important;}
}

/* ---------- Icons ---------- */
.ico{display:inline-flex;width:16px;height:16px;flex:0 0 auto;}
.ico svg{width:100%;height:100%;display:block;}

/* ---------- Login ---------- */
.login-screen{position:fixed;inset:0;z-index:100;background:var(--bg);display:flex;align-items:center;justify-content:center;padding:20px;}
.login-card{position:relative;width:100%;max-width:400px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:32px 28px;text-align:center;box-shadow:var(--shadow);}
.login-logo{width:56px;height:56px;margin:0 auto 14px;border-radius:16px;background:var(--accent-soft);border:1px solid var(--accent);display:flex;align-items:center;justify-content:center;color:var(--accent);}
.login-logo .ico{width:28px;height:28px;}
.login-card h1{font-size:20px;margin-bottom:6px;}
.login-sub{color:var(--text-muted);font-size:13px;margin:0 0 22px;}
.login-card .lang-switch{position:absolute;top:14px;right:14px;}
.password-field{position:relative;margin-bottom:6px;}
.password-field input{width:100%;padding-right:44px !important;}
.password-field .icon-btn{position:absolute;right:4px;top:50%;transform:translateY(-50%);}
.login-error{color:var(--red);min-height:18px;font-size:12px;margin:8px 0;}

/* ---------- Buttons & inputs ---------- */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:38px;padding:8px 14px;border-radius:8px;border:1px solid var(--border);background:var(--surface-2);color:var(--text);font:inherit;font-size:13px;font-weight:600;cursor:pointer;transition:background .15s,border-color .15s,color .15s,transform .05s;}
.btn:hover{border-color:var(--border-strong);background:var(--surface-3);}
.btn:active{transform:translateY(1px);}
.btn:disabled{opacity:.5;cursor:not-allowed;}
.btn-block{width:100%;}
.btn-sm{min-height:32px;padding:5px 10px;font-size:12px;}
.btn-primary{background:var(--accent);border-color:var(--accent);color:#fff;}
.btn-primary:hover{background:var(--accent-hover);border-color:var(--accent-hover);}
.btn-success{background:var(--green);border-color:var(--green);color:#fff;}
.btn-success:hover{filter:brightness(1.08);background:var(--green);}
.btn-danger{background:var(--red);border-color:var(--red);color:#fff;}
.btn-danger:hover{filter:brightness(1.08);background:var(--red);}
.btn-ghost{background:transparent;border-color:transparent;color:var(--text-muted);}
.btn-ghost:hover{background:var(--surface-3);border-color:transparent;color:var(--text);}
.icon-btn{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:8px;border:1px solid transparent;background:transparent;color:var(--text-muted);cursor:pointer;transition:background .15s,color .15s;}
.icon-btn:hover:not(:disabled){background:var(--surface-3);color:var(--text);}
.icon-btn:disabled{opacity:.45;cursor:not-allowed;}
input[type="text"],input[type="password"],input[type="number"],select,textarea{background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:9px 11px;font:inherit;font-size:13px;outline:none;transition:border-color .15s;}
input:focus,select:focus,textarea:focus{border-color:var(--accent);}
input::placeholder,textarea::placeholder{color:var(--text-faint);}
label{display:flex;flex-direction:column;gap:5px;color:var(--text-muted);font-size:12px;font-weight:600;}

/* ---------- Layout ---------- */
.container{max-width:1440px;margin:0 auto;padding:16px;display:grid;gap:16px;}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px;}
.panel-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px;}
.count{color:var(--text-faint);font-size:12px;font-weight:600;background:var(--bg);border:1px solid var(--border);border-radius:999px;padding:2px 10px;}

/* ---------- Header ---------- */
.header{display:flex;align-items:center;gap:14px;flex-wrap:wrap;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:10px 16px;}
.logo{display:flex;align-items:center;gap:9px;font-size:16px;font-weight:700;letter-spacing:.3px;}
.logo-mark{width:30px;height:30px;border-radius:9px;background:var(--accent-soft);border:1px solid var(--accent);color:var(--accent);display:flex;align-items:center;justify-content:center;}
.logo-mark .ico{width:17px;height:17px;}
.pill{display:inline-flex;align-items:center;gap:6px;background:var(--bg);border:1px solid var(--border);border-radius:999px;padding:4px 12px;color:var(--text-muted);font-size:12px;}
.pill b{color:var(--text);font-weight:600;font-variant-numeric:tabular-nums;}
.header-right{margin-left:auto;display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
.tunnel{display:flex;align-items:center;gap:6px;background:var(--bg);border:1px solid var(--border);border-radius:999px;padding:3px 4px 3px 12px;max-width:100%;}
.tunnel-url{color:var(--accent);font-family:var(--mono);font-size:12px;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-decoration:none;}
.tunnel-url:hover{text-decoration:underline;}

/* ---------- Language ---------- */
.lang-switch{display:flex;gap:4px;background:var(--bg);border:1px solid var(--border);border-radius:999px;padding:3px;}
.lang-btn{display:inline-flex;align-items:center;gap:6px;background:transparent;border:none;border-radius:999px;padding:4px 10px;color:var(--text-muted);font:inherit;font-size:12px;font-weight:600;cursor:pointer;transition:background .15s,color .15s;}
.lang-btn:hover{color:var(--text);}
.lang-btn.active{background:var(--accent-soft);color:var(--accent);}
.lang-btn .flag{width:18px;height:12px;border-radius:2px;display:block;flex:0 0 auto;}

/* ---------- Stat cards ---------- */
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;}
.stat-card{display:flex;align-items:center;gap:12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:14px 16px;}
.stat-ico{width:38px;height:38px;border-radius:10px;background:var(--bg);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;color:var(--text-muted);}
.stat-ico .ico{width:18px;height:18px;}
.stat-value{font-size:22px;font-weight:700;line-height:1.2;font-variant-numeric:tabular-nums;}
.stat-label{color:var(--text-muted);font-size:12px;font-weight:600;}
.stat-card.online .stat-ico{color:var(--green);border-color:var(--green);background:rgba(35,165,90,.12);}
.stat-card.voice .stat-ico{color:var(--accent);border-color:var(--accent);background:var(--accent-soft);}
.stat-card.errors .stat-ico{color:var(--red);border-color:var(--red);background:rgba(242,63,67,.12);}
.stat-card.errors.has-errors .stat-value{color:var(--red);}

/* ---------- Main grid ---------- */
.main-grid{display:grid;grid-template-columns:minmax(0,1fr) 400px;gap:16px;align-items:start;}
.side-col{display:grid;gap:16px;position:sticky;top:16px;}
@media (max-width:1180px){
  .main-grid{grid-template-columns:1fr;}
  .side-col{position:static;}
}

/* ---------- Bot cards ---------- */
.bots-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px;}
.bot-card{background:var(--surface-2);border:1px solid var(--border);border-radius:var(--radius);padding:12px;display:flex;flex-direction:column;gap:10px;transition:border-color .15s;}
.bot-card:hover{border-color:var(--border-strong);}
.bot-top{display:flex;align-items:center;gap:10px;}
.avatar{width:40px;height:40px;border-radius:50%;object-fit:cover;flex:0 0 auto;}
.avatar-fallback{display:inline-flex;align-items:center;justify-content:center;background:var(--surface-3);color:var(--text-muted);border:1px solid var(--border);}
.avatar-fallback .ico{width:18px;height:18px;}
.bot-id{min-width:0;flex:1;}
.bot-name{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.bot-token{color:var(--text-faint);font-size:11px;font-family:var(--mono);}
.badge{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-size:10.5px;font-weight:700;letter-spacing:.4px;border:1px solid;white-space:nowrap;}
.badge .dot{flex:0 0 auto;}
.badge-voice{color:var(--green);border-color:var(--green);background:rgba(35,165,90,.12);}
.badge-ready{color:var(--yellow);border-color:var(--yellow);background:rgba(240,178,50,.12);}
.badge-error{color:var(--red);border-color:var(--red);background:rgba(242,63,67,.12);}
.badge-connecting{color:var(--gray);border-color:var(--gray);background:rgba(128,132,142,.12);}
.bot-details{display:flex;flex-wrap:wrap;gap:10px;color:var(--text-muted);font-size:12px;}
.bot-details span{display:inline-flex;align-items:center;gap:5px;font-variant-numeric:tabular-nums;}
.bot-details .ico{width:13px;height:13px;}
.bot-error{color:var(--red);font-size:11.5px;background:rgba(242,63,67,.08);border:1px solid rgba(242,63,67,.35);border-radius:8px;padding:6px 8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.bot-controls{display:flex;gap:8px;margin-top:auto;}
.toggle-btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;flex:1;min-height:36px;padding:6px 8px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text-muted);font:inherit;font-size:12px;font-weight:600;cursor:pointer;transition:background .15s,border-color .15s,color .15s;}
.toggle-btn:hover{border-color:var(--accent);color:var(--text);}
.toggle-btn.on{background:var(--accent-soft);border-color:var(--accent);color:var(--accent);}
.empty{color:var(--text-muted);text-align:center;padding:26px 12px;font-size:13px;display:flex;flex-direction:column;align-items:center;gap:8px;}
.empty .ico{width:26px;height:26px;color:var(--text-faint);}

/* ---------- Controls ---------- */
.control-row{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;margin-bottom:10px;}
.control-row:last-child{margin-bottom:0;}
.control-row .grow{flex:1;min-width:150px;}
.control-row input,.control-row select{width:100%;}
.mode-row{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
.bulk-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;}
.bulk-grid .btn{min-height:36px;font-size:12px;}

/* ---------- Log console ---------- */
.log-console{height:300px;overflow-y:auto;background:#0f1014;border:1px solid var(--border);border-radius:var(--radius);padding:10px;font-family:var(--mono);font-size:12px;line-height:1.55;}
.log-line{white-space:pre-wrap;word-break:break-word;}
.log-info{color:var(--text);}
.log-warning{color:var(--yellow);}
.log-error{color:var(--red);}
.log-debug{color:var(--text-faint);}

/* ---------- Token manager ---------- */
.token-head{display:flex;align-items:center;gap:10px;width:100%;background:none;border:none;color:var(--text);font:inherit;cursor:pointer;padding:2px;text-align:left;}
.token-count{color:var(--text-faint);font-size:12px;margin-left:auto;}
.chevron{display:inline-flex;color:var(--text-muted);transition:transform .18s;}
.token-head.open .chevron{transform:rotate(180deg);}
#token-textarea{width:100%;height:180px;resize:vertical;font-family:var(--mono);font-size:12px;margin:14px 0 10px;}
.token-actions{display:flex;justify-content:flex-end;}

/* ---------- Channel picker & chat ---------- */
.channel-list{display:grid;gap:6px;max-height:320px;overflow-y:auto;margin:4px 0 16px;}
.channel-item{display:flex;flex-direction:column;gap:2px;width:100%;text-align:left;background:var(--surface-2);border:1px solid var(--border);border-radius:8px;padding:10px 12px;color:var(--text);font:inherit;font-size:13px;cursor:pointer;transition:border-color .15s,background .15s;}
.channel-item:hover{border-color:var(--accent);background:var(--surface-3);}
.channel-meta{color:var(--text-faint);font-size:11.5px;}
.muted{color:var(--text-muted);font-size:13px;}
.modal label{margin-bottom:12px;}
.modal label textarea,.modal label input{width:100%;}
#chatall-message{width:100%;height:70px;resize:vertical;font-size:13px;}
#chat-message{width:100%;height:80px;resize:vertical;}

/* ---------- Message reaction ---------- */
.reaction-emoji{display:flex;align-items:flex-end;gap:10px;margin-bottom:10px;}
.reaction-emoji label{flex:1;min-width:0;}
.emoji-preview{width:54px;height:42px;display:flex;align-items:center;justify-content:center;background:var(--bg);border:1px solid var(--border);border-radius:8px;font-size:20px;overflow:hidden;white-space:nowrap;flex:0 0 auto;}
.emoji-picker{display:grid;grid-template-columns:repeat(8,1fr);gap:6px;background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:10px;margin-bottom:10px;max-height:190px;overflow-y:auto;}
.emoji-option{display:flex;align-items:center;justify-content:center;font-size:20px;line-height:1;height:36px;background:transparent;border:1px solid transparent;border-radius:8px;cursor:pointer;}
.emoji-option:hover,.emoji-option:focus-visible{background:var(--surface-3);border-color:var(--border-strong);}
.spinner{width:14px;height:14px;border-radius:50%;border:2px solid rgba(255,255,255,.35);border-top-color:#fff;animation:spin .7s linear infinite;display:inline-block;flex:0 0 auto;}
@keyframes spin{to{transform:rotate(360deg);}}
input.invalid{border-color:var(--red) !important;}

/* ---------- Toasts ---------- */
.toast-container{position:fixed;top:16px;right:16px;z-index:300;display:flex;flex-direction:column;gap:8px;width:min(360px,calc(100vw - 32px));}
.toast{display:flex;align-items:flex-start;gap:10px;background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:10px;padding:12px 14px;box-shadow:var(--shadow);font-size:13px;cursor:pointer;animation:toast-in .18s ease-out;}
.toast.success{border-left-color:var(--green);}
.toast.error{border-left-color:var(--red);}
.toast .ico{width:16px;height:16px;margin-top:1px;}
.toast.success .ico{color:var(--green);}
.toast.error .ico{color:var(--red);}
.toast.info .ico{color:var(--accent);}
@keyframes toast-in{from{opacity:0;transform:translateY(-8px);}to{opacity:1;transform:none;}}

/* ---------- Modal ---------- */
.modal-backdrop{position:fixed;inset:0;z-index:200;background:rgba(0,0,0,.65);display:flex;align-items:center;justify-content:center;padding:20px;}
.modal{width:100%;max-width:420px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:20px;box-shadow:var(--shadow);}
.modal p{color:var(--text-muted);font-size:13px;margin:0 0 18px;}
.modal-actions{display:flex;justify-content:flex-end;gap:10px;}

/* ---------- Responsive ---------- */
@media (max-width:860px){
  .container{padding:10px;gap:12px;}
  .header{gap:10px;}
  .header-right{margin-left:0;width:100%;}
  .tunnel-url{max-width:150px;}
  .stats-grid{grid-template-columns:repeat(2,1fr);}
  .bots-grid{grid-template-columns:1fr;}
  .toggle-btn{min-height:44px;}
  .btn{min-height:44px;}
  .bulk-grid{grid-template-columns:repeat(2,1fr);}
  .emoji-picker{grid-template-columns:repeat(6,1fr);}
  .reaction-emoji{flex-wrap:wrap;}
  .toast-container{top:auto;bottom:16px;right:10px;left:10px;width:auto;}
}
</style>
</head>
<body>

<div id="toast-container" class="toast-container" aria-live="polite" aria-atomic="false"></div>

<div id="confirm-modal" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-message">
  <div class="modal">
    <h3 id="confirm-title">Confirm action</h3>
    <p id="confirm-message"></p>
    <div class="modal-actions">
      <button id="confirm-cancel" class="btn" type="button">Cancel</button>
      <button id="confirm-ok" class="btn btn-danger" type="button">Confirm</button>
    </div>
  </div>
</div>

<div id="move-modal" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="move-title">
  <div class="modal">
    <h3 id="move-title" data-i18n="move_title">Move to voice channel</h3>
    <div id="move-channels" class="channel-list"></div>
    <div class="modal-actions">
      <button id="move-cancel" class="btn" type="button" data-i18n="btn_cancel">Cancel</button>
    </div>
  </div>
</div>

<div id="chat-modal" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="chat-title">
  <div class="modal">
    <h3 id="chat-title" data-i18n="chat_title">Send message</h3>
    <label><span data-i18n="lbl_channel_id">Channel ID</span>
      <input id="chat-channel" type="text" data-i18n-ph="ph_text_channel" placeholder="Text channel ID">
    </label>
    <label><span data-i18n="lbl_message">Message</span>
      <textarea id="chat-message" data-i18n-ph="ph_message" placeholder="Message content..."></textarea>
    </label>
    <div class="modal-actions">
      <button id="chat-cancel" class="btn" type="button" data-i18n="btn_cancel">Cancel</button>
      <button id="chat-send" class="btn btn-primary" type="button" data-i18n="btn_send">Send</button>
    </div>
  </div>
</div>

<div id="login-screen" class="login-screen">
  <div class="login-card">
    <div class="lang-switch">
      <button class="lang-btn" data-lang="en" type="button" aria-pressed="false" data-i18n-title="lang_english">
        <span class="flag" data-flag="en"></span><span>EN</span>
      </button>
      <button class="lang-btn" data-lang="vi" type="button" aria-pressed="false" data-i18n-title="lang_vietnamese">
        <span class="flag" data-flag="vi"></span><span>VI</span>
      </button>
    </div>
    <div class="login-logo"><span class="ico" data-icon="bot"></span></div>
    <h1>kwishtt</h1>
    <p class="login-sub" data-i18n="login_sub">Sign in to manage your voice system</p>
    <div class="password-field">
      <input id="password-input" type="password" data-i18n-ph="ph_password" placeholder="Dashboard password" autocomplete="current-password" aria-label="Password">
      <button id="password-toggle" class="icon-btn" type="button" data-i18n-title="title_show_password" aria-label="Show password">
        <span class="ico" data-icon="eye"></span>
      </button>
    </div>
    <div class="login-error" id="login-error" role="alert"></div>
    <button id="login-btn" class="btn btn-primary btn-block" type="button" data-i18n="btn_login">Login</button>
  </div>
</div>

<div id="dashboard" class="hidden">
  <div class="container">

    <header class="header">
      <span class="logo"><span class="logo-mark"><span class="ico" data-icon="bot"></span></span>kwishtt</span>
      <span class="pill"><span data-i18n="stats_mode">Mode</span>: <b id="stat-mode">—</b></span>
      <span class="pill"><span data-i18n="stats_uptime">Uptime</span>: <b id="stat-uptime">00:00:00</b></span>
      <span class="pill"><span class="ico" data-icon="key"></span><span data-i18n="stats_tokens">Tokens</span>: <b id="stat-tokens">0</b></span>
      <div class="header-right">
        <span class="tunnel">
          <span class="ico" data-icon="globe" title="Tunnel"></span>
          <a id="tunnel-url" class="tunnel-url" href="#" target="_blank" rel="noopener">-</a>
          <button id="copy-tunnel" class="icon-btn" type="button" disabled data-i18n-title="title_copy_tunnel" aria-label="Copy tunnel URL">
            <span class="ico" data-icon="copy"></span>
          </button>
        </span>
        <div class="lang-switch">
          <button class="lang-btn" data-lang="en" type="button" aria-pressed="false" data-i18n-title="lang_english">
            <span class="flag" data-flag="en"></span><span>EN</span>
          </button>
          <button class="lang-btn" data-lang="vi" type="button" aria-pressed="false" data-i18n-title="lang_vietnamese">
            <span class="flag" data-flag="vi"></span><span>VI</span>
          </button>
        </div>
        <button id="logout-btn" class="btn btn-ghost" type="button">
          <span class="ico" data-icon="logout"></span><span data-i18n="btn_logout">Logout</span>
        </button>
      </div>
    </header>

    <section class="stats-grid">
      <div class="stat-card">
        <span class="stat-ico"><span class="ico" data-icon="server"></span></span>
        <div><div class="stat-value" id="stat-total">0</div><div class="stat-label" data-i18n="stat_total">Total Bots</div></div>
      </div>
      <div class="stat-card online">
        <span class="stat-ico"><span class="ico" data-icon="wifi"></span></span>
        <div><div class="stat-value" id="stat-online">0</div><div class="stat-label" data-i18n="stat_online">Online</div></div>
      </div>
      <div class="stat-card voice">
        <span class="stat-ico"><span class="ico" data-icon="volume"></span></span>
        <div><div class="stat-value" id="stat-voice">0</div><div class="stat-label" data-i18n="stat_in_voice">In Voice</div></div>
      </div>
      <div class="stat-card errors" id="stat-errors-card">
        <span class="stat-ico"><span class="ico" data-icon="alert"></span></span>
        <div><div class="stat-value" id="stat-errors">0</div><div class="stat-label" data-i18n="stat_errors">Errors</div></div>
      </div>
    </section>

    <main class="main-grid">
      <section class="panel">
        <div class="panel-head">
          <h2 data-i18n="bots_title">Bots</h2>
          <span class="count" id="bots-count">0</span>
        </div>
        <div id="bots-grid" class="bots-grid"></div>
        <div id="bot-empty" class="empty">
          <span class="ico" data-icon="server"></span>
          <span data-i18n="no_bots">No bots yet</span>
        </div>
      </section>

      <aside class="side-col">
        <section class="panel">
          <div class="panel-head"><h2 data-i18n="controls_title">Controls</h2></div>
          <div class="control-row mode-row">
            <label><span data-i18n="lbl_mode">Mode</span>
              <select id="mode-select">
                <option value="normal" data-i18n="opt_normal">Normal</option>
                <option value="auto_room" data-i18n="opt_auto_room">Auto-Room</option>
              </select>
            </label>
            <label><span data-i18n="lbl_delay">Delay (seconds)</span>
              <input id="delay-input" type="number" value="5" min="0" step="0.5">
            </label>
          </div>
          <div class="control-row">
            <label class="grow"><span data-i18n="lbl_channel_ids">Channel IDs</span>
              <input id="channel-ids" type="text" data-i18n-ph="ph_channel_ids" placeholder="e.g. 123456789 987654321">
            </label>
            <label id="leader-wrap" class="hidden"><span data-i18n="lbl_leader">Leaders</span>
              <input id="leader-count" type="number" value="5" min="1" style="width:90px">
            </label>
          </div>
          <div class="control-row">
            <button id="start-btn" class="btn btn-success grow" type="button">
              <span class="ico" data-icon="play"></span><span data-i18n="btn_start">START</span>
            </button>
            <button id="stop-btn" class="btn btn-danger grow" type="button">
              <span class="ico" data-icon="stop"></span><span data-i18n="btn_stop">STOP</span>
            </button>
          </div>
          <div class="bulk-grid">
            <button class="btn" type="button" data-toggle-field="mute" data-toggle-value="true">
              <span class="ico" data-icon="mic"></span><span data-i18n="btn_mute_all">Mute All</span>
            </button>
            <button class="btn" type="button" data-toggle-field="mute" data-toggle-value="false">
              <span class="ico" data-icon="micOff"></span><span data-i18n="btn_unmute_all">Unmute All</span>
            </button>
            <button class="btn" type="button" data-toggle-field="deaf" data-toggle-value="true">
              <span class="ico" data-icon="deaf"></span><span data-i18n="btn_deaf_all">Deaf All</span>
            </button>
            <button class="btn" type="button" data-toggle-field="deaf" data-toggle-value="false">
              <span class="ico" data-icon="deafOff"></span><span data-i18n="btn_undeaf_all">Undeaf All</span>
            </button>
            <button class="btn" type="button" data-toggle-field="video" data-toggle-value="true">
              <span class="ico" data-icon="cam"></span><span data-i18n="btn_cam_on">Cam On</span>
            </button>
            <button class="btn" type="button" data-toggle-field="video" data-toggle-value="false">
              <span class="ico" data-icon="camOff"></span><span data-i18n="btn_cam_off">Cam Off</span>
            </button>
            <button class="btn" type="button" data-toggle-field="stream" data-toggle-value="true">
              <span class="ico" data-icon="screen"></span><span data-i18n="btn_stream_on">Stream On</span>
            </button>
            <button class="btn" type="button" data-toggle-field="stream" data-toggle-value="false">
              <span class="ico" data-icon="screenOff"></span><span data-i18n="btn_stream_off">Stream Off</span>
            </button>
          </div>
          <div class="control-row" style="margin-top:10px">
            <label class="grow"><span data-i18n="lbl_rename">New nickname</span>
              <input id="rename-input" type="text" data-i18n-ph="ph_rename" placeholder="Enter nickname (reset = default)">
            </label>
            <button id="rename-all-btn" class="btn" type="button">
              <span class="ico" data-icon="user"></span><span data-i18n="btn_rename_all">Rename All</span>
            </button>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head"><h2 data-i18n="chat_all_title">Chat All</h2></div>
          <div class="control-row">
            <label class="grow"><span data-i18n="lbl_channel_id">Channel ID</span>
              <input id="chatall-channel" type="text" data-i18n-ph="ph_text_channel" placeholder="Text channel ID">
            </label>
            <label><span data-i18n="lbl_delay">Delay (seconds)</span>
              <input id="chatall-delay" type="number" value="1" min="0" step="0.1" style="width:110px">
            </label>
          </div>
          <div class="control-row">
            <label class="grow"><span data-i18n="lbl_message">Message</span>
              <textarea id="chatall-message" data-i18n-ph="ph_message" placeholder="Message content..."></textarea>
            </label>
          </div>
          <div class="control-row">
            <button id="chatall-send" class="btn btn-primary btn-block" type="button">
              <span class="ico" data-icon="send"></span><span data-i18n="btn_send_all">Send to All</span>
            </button>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head"><h2 data-i18n="reaction_title">Discord Message Reaction</h2></div>
          <div class="control-row">
            <label class="grow"><span data-i18n="lbl_channel_id">Channel ID</span>
              <input id="reaction-channel" type="text" inputmode="numeric" autocomplete="off" data-i18n-ph="ph_snowflake" placeholder="e.g. 123456789012345678">
            </label>
            <label class="grow"><span data-i18n="lbl_message_id">Message ID</span>
              <input id="reaction-message" type="text" inputmode="numeric" autocomplete="off" data-i18n-ph="ph_snowflake" placeholder="e.g. 123456789012345678">
            </label>
          </div>
          <div class="reaction-emoji">
            <label><span data-i18n="lbl_emoji">Emoji</span>
              <input id="reaction-emoji-input" type="text" autocomplete="off" data-i18n-ph="ph_emoji" placeholder="Unicode emoji, :name: or name:id">
            </label>
            <div class="emoji-preview" id="reaction-preview" aria-live="polite">?</div>
            <button id="reaction-emoji-toggle" class="icon-btn" type="button" aria-expanded="false" data-i18n-title="title_choose_emoji" aria-label="Choose emoji">
              <span class="ico" data-icon="smile"></span>
            </button>
          </div>
          <div id="reaction-picker" class="emoji-picker hidden" role="listbox" aria-label="Emoji picker"></div>
          <div class="control-row">
            <button id="reaction-send" class="btn btn-primary btn-block" type="button">
              <span class="spinner hidden" id="reaction-spinner"></span>
              <span class="ico" data-icon="send"></span>
              <span data-i18n="btn_send_reaction">Send Reaction</span>
            </button>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <h2 data-i18n="log_title">Log Console</h2>
            <button id="clear-logs" class="btn btn-ghost btn-sm" type="button">
              <span class="ico" data-icon="trash"></span><span data-i18n="btn_clear_logs">Clear</span>
            </button>
          </div>
          <div id="log-console" class="log-console" role="log" aria-live="polite"></div>
        </section>
      </aside>
    </main>

    <section class="panel">
      <button class="token-head" id="token-head" type="button" aria-expanded="false" aria-controls="token-body">
        <span class="chevron"><span class="ico" data-icon="chevron"></span></span>
        <h2 data-i18n="token_title">Token Manager</h2>
        <span class="token-count" id="token-count">Managing 0 tokens</span>
      </button>
      <div id="token-body" class="hidden">
        <textarea id="token-textarea" spellcheck="false" data-i18n-ph="ph_tokens" placeholder="One token per line..."></textarea>
        <div class="token-actions">
          <button id="save-tokens" class="btn btn-primary" type="button">
            <span class="ico" data-icon="save"></span><span data-i18n="btn_save_tokens">Save Tokens</span>
          </button>
        </div>
      </div>
    </section>

  </div>
</div>

<script>
(function(){
  'use strict';

  /* ---------- SVG icons (no emoji) ---------- */
  var SVG_OPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">';
  function svg(inner){ return SVG_OPEN + inner + '</svg>'; }
  var ICONS = {
    bot: svg('<rect x="4" y="8" width="16" height="12" rx="3"/><path d="M12 8V4"/><circle cx="12" cy="3" r="1"/><line x1="9" x2="9.01" y1="13" y2="13"/><line x1="15" x2="15.01" y1="13" y2="13"/>'),
    server: svg('<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" x2="6.01" y1="6" y2="6"/><line x1="6" x2="6.01" y1="18" y2="18"/>'),
    wifi: svg('<path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" x2="12.01" y1="20" y2="20"/>'),
    volume: svg('<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>'),
    alert: svg('<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/>'),
    play: svg('<polygon points="6 3 20 12 6 21 6 3"/>'),
    stop: svg('<rect x="5" y="5" width="14" height="14" rx="2"/>'),
    mic: svg('<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/><line x1="12" y1="19" x2="12" y2="22"/>'),
    micOff: svg('<line x1="2" y1="2" x2="22" y2="22"/><path d="M9 9v3a3 3 0 0 0 4.5 2.6"/><path d="M15 9.3V5a3 3 0 0 0-5.7-1.3"/><path d="M5 10a7 7 0 0 0 10.7 6"/><path d="M19 10v2a7 7 0 0 1-.6 2.8"/><line x1="12" y1="19" x2="12" y2="22"/>'),
    deaf: svg('<path d="M3 14v-3a9 9 0 0 1 18 0v3"/><path d="M21 14v3a2 2 0 0 1-2 2h-1v-7h1a2 2 0 0 1 2 2Z"/><path d="M3 14v3a2 2 0 0 0 2 2h1v-7H5a2 2 0 0 0-2 2Z"/>'),
    deafOff: svg('<line x1="2" y1="2" x2="22" y2="22"/><path d="M3 14v-3a9 9 0 0 1 13.6-7.6"/><path d="M21 11v0"/><path d="M21 14v3a2 2 0 0 1-1.2 1.8"/><path d="M3 14v3a2 2 0 0 0 2 2h1v-7H5a2 2 0 0 0-2 2Z"/>'),
    cam: svg('<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/>'),
    camOff: svg('<line x1="2" y1="2" x2="22" y2="22"/><path d="M9.5 4h5L17 7h3a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H7"/><path d="M4 7h-.5A1.5 1.5 0 0 0 2 8.5V18a2 2 0 0 0 2 2h11"/><circle cx="12" cy="13" r="3"/>'),
    copy: svg('<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>'),
    logout: svg('<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/>'),
    trash: svg('<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'),
    chevron: svg('<path d="m6 9 6 6 6-6"/>'),
    user: svg('<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>'),
    activity: svg('<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>'),
    hash: svg('<line x1="4" x2="20" y1="9" y2="9"/><line x1="4" x2="20" y1="15" y2="15"/><line x1="10" x2="8" y1="3" y2="21"/><line x1="16" x2="14" y1="3" y2="21"/>'),
    globe: svg('<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>'),
    eye: svg('<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>'),
    eyeOff: svg('<path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.4 10.4 0 0 1 12 5c7 0 10 7 10 7a13.2 13.2 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.5 13.5 0 0 0 2 12s3 7 10 7a9.7 9.7 0 0 0 5.39-1.61"/><line x1="2" y1="2" x2="22" y2="22"/>'),
    save: svg('<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>'),
    check: svg('<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>'),
    info: svg('<circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="16" y2="12"/><line x1="12" x2="12.01" y1="8" y2="8"/>'),
    key: svg('<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>'),
    move: svg('<path d="M3 5v14"/><path d="M21 12H7"/><path d="m15 18 6-6-6-6"/>'),
    message: svg('<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'),
    send: svg('<line x1="22" x2="11" y1="2" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>'),
    smile: svg('<circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" x2="9.01" y1="9" y2="9"/><line x1="15" x2="15.01" y1="9" y2="9"/>'),
    screen: svg('<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" x2="16" y1="21" y2="21"/><line x1="12" x2="12" y1="17" y2="21"/><path d="m10 8 4 2.5-4 2.5z"/>'),
    screenOff: svg('<line x1="2" y1="2" x2="22" y2="22"/><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" x2="16" y1="21" y2="21"/><line x1="12" x2="12" y1="17" y2="21"/>')
  };
  var FLAGS = {
    en: '<svg class="flag" viewBox="0 0 60 40" aria-hidden="true"><rect width="60" height="40" fill="#012169"/><path d="M0,0 L60,40 M60,0 L0,40" stroke="#ffffff" stroke-width="8"/><path d="M0,0 L60,40 M60,0 L0,40" stroke="#c8102e" stroke-width="4"/><path d="M30,0 L30,40 M0,20 L60,20" stroke="#ffffff" stroke-width="14"/><path d="M30,0 L30,40 M0,20 L60,20" stroke="#c8102e" stroke-width="8"/></svg>',
    vi: '<svg class="flag" viewBox="0 0 60 40" aria-hidden="true"><rect width="60" height="40" fill="#da251d"/><polygon points="30,10 32.35,16.76 39.51,16.91 33.80,21.24 35.88,28.09 30,24 24.12,28.09 26.20,21.24 20.49,16.91 27.65,16.76" fill="#ffdd00"/></svg>'
  };
  function icon(name){
    return '<span class="ico">' + (ICONS[name] || '') + '</span>';
  }
  function injectAssets(root){
    (root || document).querySelectorAll('[data-icon]').forEach(function(el){
      el.innerHTML = ICONS[el.getAttribute('data-icon')] || '';
    });
    (root || document).querySelectorAll('[data-flag]').forEach(function(el){
      el.innerHTML = FLAGS[el.getAttribute('data-flag')] || '';
    });
  }

  /* ---------- i18n ---------- */
  var I18N = {
    en: {
      login_sub: 'Sign in to manage your voice system',
      ph_password: 'Dashboard password',
      btn_login: 'Login',
      title_show_password: 'Show password',
      title_hide_password: 'Hide password',
      lang_english: 'English',
      lang_vietnamese: 'Tiếng Việt',
      err_wrong_password: 'Incorrect password.',
      err_enter_password: 'Please enter a password.',
      err_connect: 'Cannot connect to the server.',
      err_session_expired: 'Session expired, please log in again.',
      stats_mode: 'Mode', stats_uptime: 'Uptime', stats_tokens: 'Tokens',
      title_copy_tunnel: 'Copy tunnel URL', btn_copy: 'Copy', title_logout: 'Logout', btn_logout: 'Logout',
      stat_total: 'Total Bots', stat_online: 'Online', stat_in_voice: 'In Voice', stat_errors: 'Errors',
      bots_title: 'Bots', no_bots: 'No bots yet',
      controls_title: 'Controls',
      lbl_mode: 'Mode', opt_normal: 'Normal', opt_auto_room: 'Auto-Room',
      lbl_channel_ids: 'Channel IDs', ph_channel_ids: 'e.g. 123456789 987654321',
      lbl_delay: 'Delay (seconds)', lbl_leader: 'Leaders',
      btn_start: 'START', btn_stop: 'STOP',
      btn_mute_all: 'Mute All', btn_unmute_all: 'Unmute All', btn_deaf_all: 'Deaf All',
      btn_undeaf_all: 'Undeaf All', btn_cam_on: 'Cam On', btn_cam_off: 'Cam Off',
      btn_stream_on: 'Stream On', btn_stream_off: 'Stream Off',
      lbl_stream: 'Stream', title_toggle_stream: 'Toggle stream',
      lbl_rename: 'New nickname', ph_rename: 'Enter nickname (reset = default)', btn_rename_all: 'Rename All',
      btn_move: 'Move', btn_chat: 'Chat',
      move_title: 'Move to voice channel', move_loading: 'Loading channels...', move_empty: 'No voice channels available.',
      chat_title: 'Send message', lbl_channel_id: 'Channel ID', ph_text_channel: 'Text channel ID',
      lbl_message: 'Message', ph_message: 'Message content...', btn_send: 'Send',
      chat_all_title: 'Chat All', btn_send_all: 'Send to All',
      reaction_title: 'Discord Message Reaction',
      lbl_message_id: 'Message ID', ph_snowflake: 'e.g. 123456789012345678',
      lbl_emoji: 'Emoji', ph_emoji: 'Unicode emoji, :name: or name:id',
      btn_send_reaction: 'Send Reaction', title_choose_emoji: 'Choose emoji',
      err_channel_id_invalid: 'Channel ID must be 17–20 digits.',
      err_enter_message_id: 'Message ID must be 17–20 digits.',
      err_emoji_empty: 'Choose or enter an emoji.',
      msg_reaction_sent: 'Successfully reacted with {n} bot(s).',
      msg_reaction_none: 'No bots reacted. Check the IDs and bot permissions.',
      log_title: 'Log Console', btn_clear_logs: 'Clear',
      token_title: 'Token Manager', token_count: 'Managing {n} tokens',
      btn_save_tokens: 'Save Tokens', ph_tokens: 'One token per line...',
      lbl_mic: 'Mic', lbl_deaf: 'Deaf', lbl_cam: 'Cam',
      title_toggle_mute: 'Toggle microphone', title_toggle_deaf: 'Toggle deafen', title_toggle_cam: 'Toggle camera',
      status_voice: 'VOICE', status_ready: 'READY', status_error: 'ERROR', status_connecting: 'CONNECTING',
      mode_idle: 'idle', mode_normal: 'normal', mode_auto_room: 'auto_room',
      msg_enter_channel: 'Enter at least one channel ID.',
      err_enter_nickname: 'Enter a new nickname.',
      err_request_failed: 'Request failed. Please try again.',
      err_server_error: 'Internal Server Error. Please try again.',
      msg_started_normal: 'Started normal mode with {n} channel(s).',
      msg_started_auto: 'Started auto-room mode at lobby {id} with {n} leader(s).',
      msg_stopped: 'All bots stopped.',
      msg_sent_command: '{action}: {n} bot(s).',
      msg_renamed: 'Renamed {n} bot(s).',
      msg_no_bots: 'No bots affected.',
      msg_moved: 'Moved {n} bot(s).',
      msg_chat_sent: 'Message sent.',
      msg_chat_all_sent: 'Sent by {n} bot(s).',
      err_enter_message: 'Enter a message.',
      err_enter_channel_id: 'Enter a text channel ID.',
      msg_not_logged_in: 'Not logged in',
      msg_copied: 'Tunnel URL copied.', msg_copy_failed: 'Could not copy the URL.',
      msg_tokens_saved: 'Saved {n} tokens.', msg_logs_cleared: 'Logs cleared.',
      msg_saved: 'Saved successfully.',
      confirm_title: 'Confirm action',
      confirm_stop_msg: 'Stop all bots and disconnect them from voice channels?',
      confirm_save_tokens_msg: 'Save tokens to the file? The old content will be backed up to tokens.txt.bak.',
      confirm_rename_all_msg: 'Rename all online bots?',
      btn_confirm: 'Confirm', btn_cancel: 'Cancel',
      title_clear_logs: 'Clear logs'
    },
    vi: {
      login_sub: 'Đăng nhập để quản lý hệ thống voice',
      ph_password: 'Mật khẩu dashboard',
      btn_login: 'Đăng nhập',
      title_show_password: 'Hiện mật khẩu',
      title_hide_password: 'Ẩn mật khẩu',
      lang_english: 'English',
      lang_vietnamese: 'Tiếng Việt',
      err_wrong_password: 'Sai mật khẩu.',
      err_enter_password: 'Vui lòng nhập mật khẩu.',
      err_connect: 'Không kết nối được server.',
      err_session_expired: 'Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.',
      stats_mode: 'Chế độ', stats_uptime: 'Thời gian chạy', stats_tokens: 'Tổng Token',
      title_copy_tunnel: 'Copy URL tunnel', btn_copy: 'Copy', title_logout: 'Đăng xuất', btn_logout: 'Đăng xuất',
      stat_total: 'Tổng số Bot', stat_online: 'Online', stat_in_voice: 'Trong Voice', stat_errors: 'Lỗi',
      bots_title: 'Bot', no_bots: 'Chưa có bot nào',
      controls_title: 'Điều khiển',
      lbl_mode: 'Chế độ', opt_normal: 'Normal', opt_auto_room: 'Auto-Room',
      lbl_channel_ids: 'Channel IDs', ph_channel_ids: 'VD: 123456789 987654321',
      lbl_delay: 'Delay (giây)', lbl_leader: 'Số leader',
      btn_start: 'START', btn_stop: 'STOP',
      btn_mute_all: 'Tắt Mic', btn_unmute_all: 'Bật Mic', btn_deaf_all: 'Tắt Tai Nghe',
      btn_undeaf_all: 'Bật Tai Nghe', btn_cam_on: 'Bật Cam', btn_cam_off: 'Tắt Cam',
      btn_stream_on: 'Bật Stream', btn_stream_off: 'Tắt Stream',
      lbl_stream: 'Luồng', title_toggle_stream: 'Bật/tắt phát trực tiếp',
      lbl_rename: 'Nickname mới', ph_rename: 'Nhập nickname (reset = mặc định)', btn_rename_all: 'Đổi tên tất cả',
      btn_move: 'Di chuyển', btn_chat: 'Chat',
      move_title: 'Di chuyển tới voice channel', move_loading: 'Đang tải danh sách kênh...', move_empty: 'Không có voice channel khả dụng.',
      chat_title: 'Gửi tin nhắn', lbl_channel_id: 'ID kênh', ph_text_channel: 'ID kênh văn bản',
      lbl_message: 'Nội dung', ph_message: 'Nội dung tin nhắn...', btn_send: 'Gửi',
      chat_all_title: 'Chat All', btn_send_all: 'Gửi tất cả',
      reaction_title: 'Reaction Tin Nhắn Discord',
      lbl_message_id: 'ID tin nhắn', ph_snowflake: 'VD: 123456789012345678',
      lbl_emoji: 'Emoji', ph_emoji: 'Emoji Unicode, :name: hoặc name:id',
      btn_send_reaction: 'Gửi Reaction', title_choose_emoji: 'Chọn emoji',
      err_channel_id_invalid: 'ID kênh phải gồm 17–20 chữ số.',
      err_enter_message_id: 'ID tin nhắn phải gồm 17–20 chữ số.',
      err_emoji_empty: 'Chọn hoặc nhập emoji.',
      msg_reaction_sent: 'Đã thả reaction bằng {n} bot.',
      msg_reaction_none: 'Không có bot nào thả reaction. Kiểm tra ID và quyền của bot.',
      log_title: 'Log Console', btn_clear_logs: 'Xóa log',
      token_title: 'Quản lý Token', token_count: 'Đang quản lý {n} tokens',
      btn_save_tokens: 'Lưu Token', ph_tokens: 'Mỗi dòng một token...',
      lbl_mic: 'Mic', lbl_deaf: 'Tai nghe', lbl_cam: 'Cam',
      title_toggle_mute: 'Bật/tắt mic', title_toggle_deaf: 'Bật/tắt tai nghe', title_toggle_cam: 'Bật/tắt camera',
      status_voice: 'VOICE', status_ready: 'SẴN SÀNG', status_error: 'LỖI', status_connecting: 'ĐANG KẾT NỐI',
      mode_idle: 'chờ', mode_normal: 'normal', mode_auto_room: 'auto_room',
      msg_enter_channel: 'Nhập ít nhất một channel ID.',
      err_enter_nickname: 'Nhập nickname mới.',
      err_request_failed: 'Yêu cầu thất bại, vui lòng thử lại.',
      err_server_error: 'Lỗi máy chủ (500). Vui lòng thử lại.',
      msg_started_normal: 'Đã bắt đầu chế độ normal với {n} channel.',
      msg_started_auto: 'Đã bắt đầu chế độ auto_room tại lobby {id} với {n} leader.',
      msg_stopped: 'Đã dừng tất cả bots.',
      msg_sent_command: '{action}: {n} bot.',
      msg_renamed: 'Đã đổi tên {n} bot.',
      msg_no_bots: 'Không có bot nào bị ảnh hưởng.',
      msg_moved: 'Đã di chuyển {n} bot.',
      msg_chat_sent: 'Đã gửi tin nhắn.',
      msg_chat_all_sent: 'Đã gửi bằng {n} bot.',
      err_enter_message: 'Nhập nội dung tin nhắn.',
      err_enter_channel_id: 'Nhập ID kênh văn bản.',
      msg_not_logged_in: 'Chưa đăng nhập',
      msg_copied: 'Đã copy tunnel URL.', msg_copy_failed: 'Không copy được URL.',
      msg_tokens_saved: 'Đã lưu {n} tokens.', msg_logs_cleared: 'Đã xóa log.',
      msg_saved: 'Đã lưu thành công.',
      confirm_title: 'Xác nhận hành động',
      confirm_stop_msg: 'Dừng toàn bộ bot và ngắt kết nối khỏi voice?',
      confirm_save_tokens_msg: 'Lưu tokens vào file? Nội dung cũ sẽ được sao lưu vào tokens.txt.bak.',
      confirm_rename_all_msg: 'Đổi tên toàn bộ bot đang online?',
      btn_confirm: 'Xác nhận', btn_cancel: 'Hủy',
      title_clear_logs: 'Xóa log'
    }
  };
  var lang = localStorage.getItem('mgl_lang') === 'vi' ? 'vi' : 'en';
  function t(key){
    var table = I18N[lang] || I18N.en;
    return table[key] || I18N.en[key] || key;
  }
  function tOr(key, fallback){
    var table = I18N[lang] || I18N.en;
    return table[key] || I18N.en[key] || fallback;
  }

  function $(id){ return document.getElementById(id); }
  function esc(value){
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function(ch){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];
    });
  }

  /* ---------- Elements ---------- */
  var loginScreen = $('login-screen'), dashboard = $('dashboard');
  var passwordInput = $('password-input'), loginBtn = $('login-btn'), loginError = $('login-error');
  var passwordToggle = $('password-toggle');
  var statTotal = $('stat-total'), statOnline = $('stat-online'), statVoice = $('stat-voice');
  var statErrors = $('stat-errors'), statErrorsCard = $('stat-errors-card');
  var statMode = $('stat-mode'), statUptime = $('stat-uptime'), statTokens = $('stat-tokens');
  var tunnelLabel = $('tunnel-url'), copyBtn = $('copy-tunnel'), logoutBtn = $('logout-btn');
  var modeSelect = $('mode-select'), channelIdsInput = $('channel-ids'), delayInput = $('delay-input');
  var leaderWrap = $('leader-wrap'), leaderCountInput = $('leader-count');
  var startBtn = $('start-btn'), stopBtn = $('stop-btn');
  var renameInput = $('rename-input'), renameAllBtn = $('rename-all-btn');
  var botsGrid = $('bots-grid'), botsCount = $('bots-count'), botEmpty = $('bot-empty');
  var logConsole = $('log-console'), clearLogsBtn = $('clear-logs');
  var tokenHead = $('token-head'), tokenBody = $('token-body'), tokenTextarea = $('token-textarea');
  var saveTokensBtn = $('save-tokens'), tokenCount = $('token-count');
  var toastContainer = $('toast-container');
  var confirmModal = $('confirm-modal'), confirmTitle = $('confirm-title'), confirmMessage = $('confirm-message');
  var confirmOk = $('confirm-ok'), confirmCancel = $('confirm-cancel');
  var moveModal = $('move-modal'), moveChannels = $('move-channels'), moveCancel = $('move-cancel');
  var chatModal = $('chat-modal'), chatChannel = $('chat-channel'), chatMessage = $('chat-message');
  var chatCancel = $('chat-cancel'), chatSend = $('chat-send');
  var chatAllChannel = $('chatall-channel'), chatAllMessage = $('chatall-message');
  var chatAllDelay = $('chatall-delay'), chatAllSend = $('chatall-send');
  var reactionChannel = $('reaction-channel'), reactionMessage = $('reaction-message');
  var reactionEmoji = $('reaction-emoji-input'), reactionPreview = $('reaction-preview');
  var reactionPicker = $('reaction-picker'), reactionToggle = $('reaction-emoji-toggle');
  var reactionSend = $('reaction-send'), reactionSpinner = $('reaction-spinner');

  var TOKEN_KEY = 'mgl_dashboard_token';
  var CHAT_CHANNEL_KEY = 'mgl_chat_channel';
  var token = localStorage.getItem(TOKEN_KEY) || '';
  var ws = null, wsRetryTimer = null, authFailed = false;
  var baseUptime = 0, baseUptimeStamp = Date.now();
  var lastSummary = null, lastTokenCount = 0, loginErrorKey = '';
  var moveBotId = '', chatBotId = '';

  /* ---------- Toast ---------- */
  function toast(message, type){
    var el = document.createElement('div');
    el.className = 'toast ' + (type || 'info');
    el.setAttribute('role', 'status');
    el.innerHTML = icon(type === 'success' ? 'check' : (type === 'error' ? 'alert' : 'info'))
      + '<span>' + esc(message) + '</span>';
    el.addEventListener('click', function(){ el.remove(); });
    toastContainer.appendChild(el);
    setTimeout(function(){ el.remove(); }, 4000);
  }

  /* ---------- Confirm dialog ---------- */
  var confirmResolve = null, lastFocused = null;
  function askConfirm(messageKey){
    return new Promise(function(resolve){
      confirmResolve = resolve;
      lastFocused = document.activeElement;
      confirmTitle.textContent = t('confirm_title');
      confirmMessage.textContent = t(messageKey);
      confirmOk.textContent = t('btn_confirm');
      confirmCancel.textContent = t('btn_cancel');
      confirmModal.classList.remove('hidden');
      confirmOk.focus();
    });
  }
  function closeConfirm(result){
    if (confirmModal.classList.contains('hidden')) { return; }
    confirmModal.classList.add('hidden');
    if (lastFocused && lastFocused.focus) { lastFocused.focus(); }
    if (confirmResolve) { confirmResolve(result); confirmResolve = null; }
  }
  confirmOk.addEventListener('click', function(){ closeConfirm(true); });
  confirmCancel.addEventListener('click', function(){ closeConfirm(false); });
  confirmModal.addEventListener('click', function(event){
    if (event.target === confirmModal) { closeConfirm(false); }
  });
  document.addEventListener('keydown', function(event){
    if (event.key !== 'Escape') { return; }
    closeConfirm(false);
    closeModal(moveModal);
    closeModal(chatModal);
    toggleEmojiPicker(false);
  });

  /* ---------- i18n apply ---------- */
  function setLoginError(key){
    loginErrorKey = key || '';
    loginError.textContent = loginErrorKey ? t(loginErrorKey) : '';
  }
  function setTokenCount(count){
    lastTokenCount = count || 0;
    tokenCount.textContent = t('token_count').replace('{n}', lastTokenCount);
  }
  function applyLanguage(){
    document.documentElement.lang = lang;
    document.querySelectorAll('[data-i18n]').forEach(function(el){
      el.textContent = t(el.getAttribute('data-i18n'));
    });
    document.querySelectorAll('[data-i18n-ph]').forEach(function(el){
      el.setAttribute('placeholder', t(el.getAttribute('data-i18n-ph')));
    });
    document.querySelectorAll('[data-i18n-title]').forEach(function(el){
      el.setAttribute('title', t(el.getAttribute('data-i18n-title')));
    });
    document.querySelectorAll('.lang-btn').forEach(function(btn){
      var active = btn.getAttribute('data-lang') === lang;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    updatePasswordToggle();
    if (loginErrorKey) { loginError.textContent = t(loginErrorKey); }
    setTokenCount(lastTokenCount);
    if (lastSummary) { renderSummary(lastSummary); }
  }
  document.addEventListener('click', function(event){
    var btn = event.target.closest('.lang-btn');
    if (!btn) { return; }
    lang = btn.getAttribute('data-lang') === 'vi' ? 'vi' : 'en';
    localStorage.setItem('mgl_lang', lang);
    applyLanguage();
  });

  /* ---------- Password toggle ---------- */
  function updatePasswordToggle(){
    var visible = passwordInput.type === 'text';
    passwordToggle.setAttribute('title', t(visible ? 'title_hide_password' : 'title_show_password'));
    passwordToggle.setAttribute('aria-label', t(visible ? 'title_hide_password' : 'title_show_password'));
    passwordToggle.querySelector('.ico').innerHTML = visible ? ICONS.eyeOff : ICONS.eye;
  }
  passwordToggle.addEventListener('click', function(){
    passwordInput.type = passwordInput.type === 'password' ? 'text' : 'password';
    updatePasswordToggle();
    passwordInput.focus();
  });

  /* ---------- API ---------- */
  function api(path, method, body){
    var headers = {};
    if (body !== null && body !== undefined) { headers['Content-Type'] = 'application/json'; }
    if (token) { headers['Authorization'] = 'Bearer ' + token; }
    return fetch(path, {
      method: method || 'POST',
      headers: headers,
      body: (body !== null && body !== undefined) ? JSON.stringify(body) : undefined
    }).then(function(res){
      if (res.status === 401) { doLogout(); return null; }
      return res.json().catch(function(){ return null; });
    }).catch(function(){ return null; });
  }
  function apiWithStatus(path, method, body){
    var headers = {};
    if (body !== null && body !== undefined) { headers['Content-Type'] = 'application/json'; }
    if (token) { headers['Authorization'] = 'Bearer ' + token; }
    return fetch(path, {
      method: method || 'POST',
      headers: headers,
      body: (body !== null && body !== undefined) ? JSON.stringify(body) : undefined
    }).then(function(res){
      if (res.status === 401) { doLogout(); return {status: 401, data: null}; }
      return res.json().then(function(data){
        return {status: res.status, data: data};
      }).catch(function(){
        return {status: res.status, data: null};
      });
    }).catch(function(){
      return {status: 0, data: null};
    });
  }

  /* ---------- Login / logout ---------- */
  function doLogin(){
    setLoginError('');
    var password = passwordInput.value;
    if (!password) { setLoginError('err_enter_password'); return; }
    loginBtn.disabled = true;
    fetch('/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({password: password})
    }).then(function(res){
      if (!res.ok) { setLoginError('err_wrong_password'); return null; }
      return res.json();
    }).then(function(data){
      if (!data) { return; }
      token = data.token;
      localStorage.setItem(TOKEN_KEY, token);
      authFailed = false;
      showDashboard();
      connectWS();
      refreshStatus();
    }).catch(function(){
      setLoginError('err_connect');
    }).then(function(){
      loginBtn.disabled = false;
    });
  }
  function doLogout(){
    token = '';
    localStorage.removeItem(TOKEN_KEY);
    authFailed = true;
    if (ws) { try { ws.close(); } catch (err) {} ws = null; }
    if (wsRetryTimer) { clearTimeout(wsRetryTimer); wsRetryTimer = null; }
    passwordInput.value = '';
    setLoginError('');
    showLogin();
  }
  loginBtn.addEventListener('click', doLogin);
  passwordInput.addEventListener('keydown', function(event){
    if (event.key === 'Enter') { doLogin(); }
  });
  logoutBtn.addEventListener('click', doLogout);

  function showLogin(){
    loginScreen.classList.remove('hidden');
    dashboard.classList.add('hidden');
  }
  function showDashboard(){
    loginScreen.classList.add('hidden');
    dashboard.classList.remove('hidden');
  }
  function isTokenExpired(jwt){
    try {
      var payload = JSON.parse(atob(jwt.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
      return payload.exp ? payload.exp * 1000 <= Date.now() : false;
    } catch (err) {
      return true;
    }
  }

  /* ---------- WebSocket ---------- */
  function connectWS(){
    if (!token) { return; }
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) { return; }
    authFailed = false;
    var proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
    ws = new WebSocket(proto + location.host + '/ws');
    ws.onopen = function(){
      try { ws.send(JSON.stringify({type: 'auth', token: token})); } catch (err) {}
    };
    ws.onmessage = function(event){
      var msg;
      try { msg = JSON.parse(event.data); } catch (err) { return; }
      handleMessage(msg);
    };
    ws.onclose = function(){
      ws = null;
      if (!token || authFailed) { return; }
      if (wsRetryTimer) { clearTimeout(wsRetryTimer); }
      wsRetryTimer = setTimeout(connectWS, 3000);
    };
  }
  function handleMessage(msg){
    if (msg.type === 'state_update') { renderSummary(msg.data || {}); }
    else if (msg.type === 'logs_history') { renderLogs(msg.data || []); }
    else if (msg.type === 'log') { appendLog(msg.data || {}); }
    else if (msg.type === 'tunnel_status') { renderTunnel(msg.data || {}); }
    else if (msg.type === 'error' && msg.message === 'Unauthorized') {
      authFailed = true;
      token = '';
      localStorage.removeItem(TOKEN_KEY);
      setLoginError('err_session_expired');
      showLogin();
    }
  }

  /* ---------- Render ---------- */
  function fmtUptime(seconds){
    seconds = Math.max(0, Math.floor(seconds));
    var h = String(Math.floor(seconds / 3600)).padStart(2, '0');
    var m = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
    var s = String(seconds % 60).padStart(2, '0');
    return h + ':' + m + ':' + s;
  }
  function renderSummary(summary){
    lastSummary = summary;
    var bots = summary.bots || [];
    var errors = bots.filter(function(bot){ return !!bot.error; }).length;

    statTotal.textContent = summary.total_bots || 0;
    statTokens.textContent = summary.total_tokens || 0;
    statOnline.textContent = summary.ready_bots || 0;
    statVoice.textContent = summary.bots_in_voice || 0;
    statErrors.textContent = errors;
    statErrorsCard.classList.toggle('has-errors', errors > 0);

    var mode = summary.active_mode || 'idle';
    statMode.textContent = tOr('mode_' + mode, mode);
    baseUptime = summary.uptime_seconds || 0;
    baseUptimeStamp = Date.now();

    renderBots(bots);
  }
  function statusOf(bot){
    if (bot.error) { return {label: t('status_error'), cls: 'badge-error'}; }
    if (bot.is_in_voice) { return {label: t('status_voice'), cls: 'badge-voice'}; }
    if (bot.ready) { return {label: t('status_ready'), cls: 'badge-ready'}; }
    return {label: t('status_connecting'), cls: 'badge-connecting'};
  }
  function toggleButton(bot, field, active, iconName, labelKey){
    return '<button class="toggle-btn' + (active ? ' on' : '') + '" type="button"'
      + ' data-bot-id="' + esc(bot.id || bot.token_masked) + '"'
      + ' data-field="' + field + '"'
      + ' data-value="' + (active ? 'false' : 'true') + '"'
      + ' title="' + esc(t('title_toggle_' + field)) + '"'
      + ' aria-pressed="' + (active ? 'true' : 'false') + '">'
      + icon(iconName) + '<span>' + esc(t(labelKey)) + '</span></button>';
  }
  function actionButton(bot, action, iconName, labelKey){
    return '<button class="toggle-btn" type="button"'
      + ' data-action="' + action + '"'
      + ' data-bot-id="' + esc(bot.id || bot.token_masked) + '"'
      + ' title="' + esc(t(labelKey)) + '">'
      + icon(iconName) + '<span>' + esc(t(labelKey)) + '</span></button>';
  }
  function botCard(bot){
    var st = statusOf(bot);
    var user = bot.user || {};
    var name = user.display_name || user.username || t('msg_not_logged_in');
    var avatar = user.avatar_url
      ? '<img class="avatar" src="' + esc(user.avatar_url) + '" alt="">'
      : '<span class="avatar avatar-fallback">' + icon('user') + '</span>';
    var ping = (typeof bot.latency_ms === 'number' && bot.latency_ms >= 0) ? bot.latency_ms + ' ms' : '—';
    var error = bot.error
      ? '<div class="bot-error" title="' + esc(bot.error) + '">' + esc(bot.error) + '</div>'
      : '';
    return '<article class="bot-card" data-bot-id="' + esc(bot.id || bot.token_masked) + '">'
      + '<div class="bot-top">' + avatar
      + '<div class="bot-id"><div class="bot-name">' + esc(name) + '</div>'
      + '<div class="bot-token">' + esc(bot.token_masked) + '</div></div>'
      + '<span class="badge ' + st.cls + '"><span class="dot"><svg viewBox="0 0 10 10" width="8" height="8"><circle cx="5" cy="5" r="4" fill="currentColor"/></svg></span>' + esc(st.label) + '</span>'
      + '</div>'
      + '<div class="bot-details">'
      + '<span title="Ping">' + icon('activity') + esc(ping) + '</span>'
      + '<span>' + icon('hash') + esc(bot.channel_name || '—') + '</span>'
      + '<span>' + icon('server') + esc(bot.guild_name || '—') + '</span>'
      + '</div>'
      + error
      + '<div class="bot-controls">'
      + toggleButton(bot, 'mute', !!bot.is_mute, bot.is_mute ? 'mic' : 'micOff', 'lbl_mic')
      + toggleButton(bot, 'deaf', !!bot.is_deaf, bot.is_deaf ? 'deaf' : 'deafOff', 'lbl_deaf')
      + toggleButton(bot, 'video', !!bot.is_video, bot.is_video ? 'cam' : 'camOff', 'lbl_cam')
      + toggleButton(bot, 'stream', !!bot.is_streaming, bot.is_streaming ? 'screen' : 'screenOff', 'lbl_stream')
      + '</div>'
      + '<div class="bot-controls">'
      + actionButton(bot, 'move', 'move', 'btn_move')
      + actionButton(bot, 'chat', 'message', 'btn_chat')
      + '</div></article>';
  }
  function renderBots(bots){
    botsCount.textContent = bots.length;
    if (!bots.length) {
      botsGrid.innerHTML = '';
      botEmpty.classList.remove('hidden');
      return;
    }
    botEmpty.classList.add('hidden');
    botsGrid.innerHTML = bots.map(botCard).join('');
  }
  function renderTunnel(status){
    var url = status.public_url || '';
    tunnelLabel.textContent = url || '—';
    tunnelLabel.href = url || '#';
    copyBtn.disabled = !url;
    copyBtn.setAttribute('data-url', url);
  }
  function refreshStatus(){
    if (!token) { return; }
    api('/api/status', 'GET').then(function(data){
      if (data) { renderTunnel(data); }
    });
  }
  function appendLog(entry){
    var line = document.createElement('div');
    var level = (entry.level || 'INFO').toLowerCase();
    line.className = 'log-line log-' + level;
    line.textContent = '[' + (entry.timestamp || '') + '] [' + (entry.level || 'INFO') + '] ' + (entry.message || '');
    logConsole.appendChild(line);
    while (logConsole.childElementCount > 500) { logConsole.removeChild(logConsole.firstChild); }
    logConsole.scrollTop = logConsole.scrollHeight;
  }
  function renderLogs(entries){
    logConsole.innerHTML = '';
    entries.forEach(appendLog);
  }

  /* ---------- Actions ---------- */
  function runToggle(payload, label){
    api('/api/toggle', 'POST', payload).then(function(data){
      if (!data) { toast(t('err_request_failed'), 'error'); return; }
      if (data.affected === 0) { toast(t('msg_no_bots'), 'error'); }
      else { toast(t('msg_sent_command').replace('{action}', label).replace('{n}', data.affected), 'success'); }
    });
  }
  document.querySelectorAll('[data-toggle-field]').forEach(function(button){
    button.addEventListener('click', function(){
      var field = button.getAttribute('data-toggle-field');
      var value = button.getAttribute('data-toggle-value') === 'true';
      var payload = {};
      payload[field] = value;
      runToggle(payload, button.textContent.trim());
    });
  });
  botsGrid.addEventListener('click', function(event){
    var actionBtn = event.target.closest('[data-action]');
    if (actionBtn) {
      var action = actionBtn.getAttribute('data-action');
      var actionBotId = actionBtn.getAttribute('data-bot-id');
      if (action === 'move') { openMoveModal(actionBotId); }
      else if (action === 'chat') { openChatModal(actionBotId); }
      return;
    }
    var button = event.target.closest('.toggle-btn');
    if (!button) { return; }
    var field = button.getAttribute('data-field');
    var labelKeys = {mute: 'lbl_mic', deaf: 'lbl_deaf', video: 'lbl_cam', stream: 'lbl_stream'};
    var fieldLabel = t(labelKeys[field] || 'lbl_cam');
    var payload = {bot_id: button.getAttribute('data-bot-id')};
    payload[field] = button.getAttribute('data-value') === 'true';
    api('/api/toggle', 'POST', payload).then(function(data){
      if (!data) { toast(t('err_request_failed'), 'error'); return; }
      if (data.affected === 0) { toast(t('msg_no_bots'), 'error'); }
      else { toast(t('msg_sent_command').replace('{action}', fieldLabel).replace('{n}', data.affected), 'success'); }
    });
  });
  startBtn.addEventListener('click', function(){
    var ids = channelIdsInput.value.split(/[\s,]+/).filter(Boolean);
    if (!ids.length) { toast(t('msg_enter_channel'), 'error'); return; }
    var payload = {
      mode: modeSelect.value,
      channel_ids: ids,
      delay: parseFloat(delayInput.value) || 0,
      leader_count: parseInt(leaderCountInput.value, 10) || 5
    };
    api('/api/start', 'POST', payload).then(function(data){
      if (!data) { toast(t('err_request_failed'), 'error'); return; }
      if (payload.mode === 'auto_room') {
        toast(t('msg_started_auto').replace('{id}', ids[0]).replace('{n}', payload.leader_count), 'success');
      } else {
        toast(t('msg_started_normal').replace('{n}', ids.length), 'success');
      }
    });
  });
  stopBtn.addEventListener('click', function(){
    askConfirm('confirm_stop_msg').then(function(ok){
      if (!ok) { return; }
      api('/api/stop', 'POST').then(function(data){
        if (!data) { toast(t('err_request_failed'), 'error'); return; }
        toast(t('msg_stopped'), 'success');
      });
    });
  });
  renameAllBtn.addEventListener('click', function(){
    var name = renameInput.value.trim();
    if (!name) { toast(t('err_enter_nickname'), 'error'); return; }
    askConfirm('confirm_rename_all_msg').then(function(ok){
      if (!ok) { return; }
      api('/api/rename', 'POST', {name: name}).then(function(data){
        if (!data) { toast(t('err_request_failed'), 'error'); return; }
        toast(t('msg_renamed').replace('{n}', data.affected), 'success');
      });
    });
  });
  clearLogsBtn.addEventListener('click', function(){
    api('/api/logs', 'DELETE').then(function(){
      logConsole.innerHTML = '';
      toast(t('msg_logs_cleared'), 'info');
    });
  });
  copyBtn.addEventListener('click', function(){
    var url = copyBtn.getAttribute('data-url') || '';
    if (!url) { return; }
    function done(){ toast(t('msg_copied'), 'success'); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(done).catch(function(){ fallbackCopy(url, done); });
    } else {
      fallbackCopy(url, done);
    }
  });
  function fallbackCopy(text, done){
    var area = document.createElement('textarea');
    area.value = text;
    document.body.appendChild(area);
    area.select();
    try { document.execCommand('copy'); done(); }
    catch (err) { toast(t('msg_copy_failed'), 'error'); }
    document.body.removeChild(area);
  }

  /* ---------- Token manager ---------- */
  tokenHead.addEventListener('click', function(){
    var opening = tokenBody.classList.contains('hidden');
    tokenBody.classList.toggle('hidden');
    tokenHead.classList.toggle('open', opening);
    tokenHead.setAttribute('aria-expanded', opening ? 'true' : 'false');
    if (opening) { loadTokens(); }
  });
  function loadTokens(){
    api('/api/tokens', 'GET').then(function(data){
      if (!data) { return; }
      tokenTextarea.value = (data.tokens || []).map(function(item){ return item.full; }).join('\n');
      setTokenCount(data.count);
    });
  }
  saveTokensBtn.addEventListener('click', function(){
    var lines = tokenTextarea.value.split('\n').map(function(item){ return item.trim(); }).filter(Boolean);
    askConfirm('confirm_save_tokens_msg').then(function(ok){
      if (!ok) { return; }
      api('/api/tokens', 'PUT', {tokens: lines}).then(function(data){
        if (!data) { toast(t('err_request_failed'), 'error'); return; }
        setTokenCount(data.count);
        toast(t('msg_tokens_saved').replace('{n}', data.count), 'success');
      });
    });
  });

  /* ---------- Message Reaction ---------- */
  var EMOJI_GRID = ['👍', '❤️', '😂', '🔥', '✅', '🎉', '😍', '😎', '🤔', '😢', '👀', '💯', '🚀', '🙏', '💪', '🤣', '😅', '😊', '🎯', '⚡', '⭐', '🥳', '💀', '🤝'];
  var SNOWFLAKE_RE = /^\d{17,20}$/;

  function renderEmojiPicker(){
    reactionPicker.innerHTML = EMOJI_GRID.map(function(emoji){
      return '<button class="emoji-option" type="button" role="option" data-emoji="' + emoji + '" title="' + emoji + '">' + emoji + '</button>';
    }).join('');
  }
  function updateReactionPreview(){
    var value = reactionEmoji.value.trim();
    reactionPreview.textContent = value || '?';
  }
  function setReactionEmoji(value){
    reactionEmoji.value = value;
    updateReactionPreview();
  }
  function toggleEmojiPicker(show){
    if (typeof show !== 'boolean') { show = reactionPicker.classList.contains('hidden'); }
    reactionPicker.classList.toggle('hidden', !show);
    reactionToggle.setAttribute('aria-expanded', show ? 'true' : 'false');
  }
  function validateSnowflake(input, errorKey){
    var ok = SNOWFLAKE_RE.test(input.value.trim());
    input.classList.toggle('invalid', !ok);
    input.setAttribute('aria-invalid', ok ? 'false' : 'true');
    if (!ok) { toast(t(errorKey), 'error'); }
    return ok;
  }
  function submitReaction(){
    var channelOk = validateSnowflake(reactionChannel, 'err_channel_id_invalid');
    var messageOk = validateSnowflake(reactionMessage, 'err_enter_message_id');
    var emoji = reactionEmoji.value.trim();
    if (!channelOk || !messageOk) { return; }
    if (!emoji) { toast(t('err_emoji_empty'), 'error'); return; }

    reactionSend.disabled = true;
    reactionSpinner.classList.remove('hidden');
    apiWithStatus('/api/reaction', 'POST', {
      channel_id: reactionChannel.value.trim(),
      message_id: reactionMessage.value.trim(),
      emoji: emoji
    }).then(function(result){
      reactionSend.disabled = false;
      reactionSpinner.classList.add('hidden');
      var data = result.data;
      if (result.status === 200 && data && data.success && typeof data.reacted === 'number') {
        if (data.reacted > 0) {
          toast(t('msg_reaction_sent').replace('{n}', data.reacted), 'success');
        } else {
          toast(t('msg_reaction_none'), 'error');
        }
        return;
      }
      if (result.status === 500 || result.status === 503) {
        toast(t('err_server_error'), 'error');
        return;
      }
      toast(data && data.detail ? String(data.detail) : t('err_request_failed'), 'error');
    });
  }
  reactionToggle.addEventListener('click', function(){ toggleEmojiPicker(); });
  reactionPicker.addEventListener('click', function(event){
    var option = event.target.closest('.emoji-option');
    if (!option) { return; }
    setReactionEmoji(option.getAttribute('data-emoji'));
    toggleEmojiPicker(false);
  });
  reactionEmoji.addEventListener('input', updateReactionPreview);
  reactionSend.addEventListener('click', submitReaction);
  document.addEventListener('click', function(event){
    if (reactionPicker.classList.contains('hidden')) { return; }
    if (event.target.closest('#reaction-picker') || event.target.closest('#reaction-emoji-toggle')) { return; }
    toggleEmojiPicker(false);
  });

  /* ---------- Modals: Move / Chat ---------- */
  function openModal(el){
    el.classList.remove('hidden');
    var first = el.querySelector('input, textarea, button');
    if (first) { first.focus(); }
  }
  function closeModal(el){
    if (el) { el.classList.add('hidden'); }
  }
  function openMoveModal(botId){
    moveBotId = botId;
    moveChannels.innerHTML = '<div class="muted">' + esc(t('move_loading')) + '</div>';
    openModal(moveModal);
    api('/api/bots/' + encodeURIComponent(botId) + '/voice-channels', 'GET').then(function(data){
      if (!data) { toast(t('err_request_failed'), 'error'); closeModal(moveModal); return; }
      var channels = data.channels || [];
      if (!channels.length) {
        moveChannels.innerHTML = '<div class="muted">' + esc(t('move_empty')) + '</div>';
        return;
      }
      moveChannels.innerHTML = channels.map(function(ch){
        var limit = ch.user_limit ? String(ch.user_limit) : '∞';
        return '<button class="channel-item" type="button" data-channel-id="' + esc(ch.id) + '">'
          + '<span>' + esc(ch.name) + '</span>'
          + '<span class="channel-meta">' + esc(ch.guild_name) + ' · ' + (ch.member_count || 0) + '/' + limit + '</span>'
          + '</button>';
      }).join('');
    });
  }
  moveChannels.addEventListener('click', function(event){
    var item = event.target.closest('.channel-item');
    if (!item || !moveBotId) { return; }
    var channelId = item.getAttribute('data-channel-id');
    api('/api/move', 'POST', {target_channel_id: channelId, bot_ids: [moveBotId]}).then(function(data){
      if (!data) { toast(t('err_request_failed'), 'error'); return; }
      toast(t('msg_moved').replace('{n}', data.moved), 'success');
      closeModal(moveModal);
    });
  });
  moveCancel.addEventListener('click', function(){ closeModal(moveModal); });
  moveModal.addEventListener('click', function(event){
    if (event.target === moveModal) { closeModal(moveModal); }
  });

  function openChatModal(botId){
    chatBotId = botId;
    chatChannel.value = localStorage.getItem(CHAT_CHANNEL_KEY) || '';
    chatMessage.value = '';
    openModal(chatModal);
    chatChannel.focus();
  }
  function sendChatSingle(){
    var channelId = chatChannel.value.trim();
    var message = chatMessage.value.trim();
    if (!channelId) { toast(t('err_enter_channel_id'), 'error'); return; }
    if (!message) { toast(t('err_enter_message'), 'error'); return; }
    localStorage.setItem(CHAT_CHANNEL_KEY, channelId);
    api('/api/chat/single', 'POST', {bot_id: chatBotId, channel_id: channelId, message: message}).then(function(data){
      if (!data || !data.sent) { toast(t('err_request_failed'), 'error'); return; }
      toast(t('msg_chat_sent'), 'success');
      closeModal(chatModal);
    });
  }
  chatSend.addEventListener('click', sendChatSingle);
  chatMessage.addEventListener('keydown', function(event){
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { sendChatSingle(); }
  });
  chatCancel.addEventListener('click', function(){ closeModal(chatModal); });
  chatModal.addEventListener('click', function(event){
    if (event.target === chatModal) { closeModal(chatModal); }
  });

  /* ---------- Chat All ---------- */
  chatAllChannel.value = localStorage.getItem(CHAT_CHANNEL_KEY) || '';
  chatAllSend.addEventListener('click', function(){
    var channelId = chatAllChannel.value.trim();
    var message = chatAllMessage.value.trim();
    var delay = parseFloat(chatAllDelay.value);
    if (!channelId) { toast(t('err_enter_channel_id'), 'error'); return; }
    if (!message) { toast(t('err_enter_message'), 'error'); return; }
    if (!isFinite(delay) || delay < 0) { delay = 0; }
    localStorage.setItem(CHAT_CHANNEL_KEY, channelId);
    chatAllSend.disabled = true;
    api('/api/chat/all', 'POST', {channel_id: channelId, message: message, delay: delay}).then(function(data){
      chatAllSend.disabled = false;
      if (!data) { toast(t('err_request_failed'), 'error'); return; }
      toast(t('msg_chat_all_sent').replace('{n}', data.sent), 'success');
    });
  });

  /* ---------- Init ---------- */
  injectAssets();
  applyLanguage();
  renderEmojiPicker();
  updateReactionPreview();
  modeSelect.addEventListener('change', function(){
    leaderWrap.classList.toggle('hidden', modeSelect.value !== 'auto_room');
  });
  setInterval(function(){
    statUptime.textContent = fmtUptime(baseUptime + (Date.now() - baseUptimeStamp) / 1000);
  }, 1000);
  setInterval(function(){ if (token) { refreshStatus(); } }, 30000);

  if (token && !isTokenExpired(token)) {
    showDashboard();
    connectWS();
    refreshStatus();
  } else {
    token = '';
    localStorage.removeItem(TOKEN_KEY);
    showLogin();
    passwordInput.focus();
  }
})();
</script>
</body>
</html>
"""
