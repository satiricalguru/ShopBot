from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import asyncio, json, os, uuid
from datetime import datetime
from dotenv import load_dotenv

# Load .env from project root (non-secret defaults only)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

from monitor import StockMonitor
from notifier import Notifier

app = FastAPI(title="ShopBot API")

# CORS is open for local dev; tighten allow_origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Persistent settings ───────────────────────────────────────────────────────
# Stored in settings.json (gitignored) so credentials survive server restarts.
# Users paste their own Telegram token + chat ID via the Settings modal in the UI.

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "settings.json")

_DEFAULTS: dict = {
    "telegram_token":        "",
    "telegram_chat_id":      "",
    "check_interval":        int(os.getenv("CHECK_INTERVAL", "30")),
    "notifications_enabled": False,
}

def _load_settings() -> dict:
    """Load from settings.json, falling back to defaults for any missing keys."""
    base = dict(_DEFAULTS)
    try:
        with open(SETTINGS_FILE, "r") as f:
            saved = json.load(f)
        base.update({k: v for k, v in saved.items() if k in base})
    except (FileNotFoundError, json.JSONDecodeError):
        pass  # first run or corrupt file — use defaults
    return base

def _save_settings(s: dict) -> None:
    """Persist settings to disk (atomic-ish write)."""
    tmp = SETTINGS_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(s, f, indent=2)
        os.replace(tmp, SETTINGS_FILE)
    except Exception as e:
        print(f"[Settings] Failed to save: {e}")

settings: dict = _load_settings()

# ─── In-memory state ──────────────────────────────────────────────────────────
watchlist: dict = {}   # id → item dict
history:   list = []   # newest-first

monitor = StockMonitor()

# ─── WebSocket manager ────────────────────────────────────────────────────────
class WSManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self.connections.remove(ws)

    async def broadcast(self, payload: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.remove(ws)

ws_manager = WSManager()

# ─── Pydantic models ──────────────────────────────────────────────────────────
class CheckReq(BaseModel):
    url: str
    pincode: Optional[str] = None

class WatchlistReq(BaseModel):
    url: str
    label:    Optional[str] = None
    interval: Optional[int] = 30
    pincode:  Optional[str] = None

class SettingsReq(BaseModel):
    telegram_token:        Optional[str]  = None
    telegram_chat_id:      Optional[str]  = None
    check_interval:        Optional[int]  = None
    notifications_enabled: Optional[bool] = None

# ─── Helpers ──────────────────────────────────────────────────────────────────
SUPPORTED_DOMAINS = ("flipkart.com", "amazon.in")

def _validate_url(url: str):
    if not any(d in url for d in SUPPORTED_DOMAINS):
        raise HTTPException(400, f"URL must be from a supported platform: {', '.join(SUPPORTED_DOMAINS)}")

async def _maybe_notify(result: dict):
    if (
        result.get("in_stock")
        and settings["notifications_enabled"]
        and settings["telegram_token"]
        and settings["telegram_chat_id"]
    ):
        n = Notifier(settings["telegram_token"], settings["telegram_chat_id"])
        await n.notify_stock(result.get("title", ""), result.get("url", ""), result.get("platform", ""))

def _make_history_entry(result: dict) -> dict:
    return {
        "id":             str(uuid.uuid4()),
        "url":            result.get("url", ""),
        "title":          result.get("title", "Unknown"),
        "in_stock":       result.get("in_stock", False),
        "stock_label":    result.get("stock_label", ""),
        "price":          result.get("price"),
        "image":          result.get("image"),
        "pincode":        result.get("pincode"),
        "pincode_result": result.get("pincode_result"),
        "platform":       result.get("platform", ""),
        "timestamp":      datetime.now().isoformat(),
        "error":          result.get("error"),
    }

# ─── Endpoints ────────────────────────────────────────────────────────────────
@app.post("/api/check")
async def check_stock(req: CheckReq):
    _validate_url(req.url)
    result = await monitor.check_once(req.url, pincode=req.pincode)
    entry  = _make_history_entry(result)
    history.insert(0, entry)
    if len(history) > 200:
        history.pop()
    await ws_manager.broadcast({"type": "history_update", "data": entry})
    await _maybe_notify(result)
    return {**result, "history_id": entry["id"]}

@app.get("/api/history")
async def get_history(limit: int = 50):
    return history[:limit]

@app.delete("/api/history")
async def clear_history():
    history.clear()
    await ws_manager.broadcast({"type": "history_clear"})
    return {"ok": True}

@app.get("/api/watchlist")
async def get_watchlist():
    return list(watchlist.values())

@app.post("/api/watchlist")
async def add_watchlist(req: WatchlistReq):
    _validate_url(req.url)
    item_id = str(uuid.uuid4())
    item = {
        "id":             item_id,
        "url":            req.url,
        "label":          req.label or req.url[:60] + ("…" if len(req.url) > 60 else ""),
        "interval":       req.interval or 30,
        "status":         "pending",
        "title":          None,
        "price":          None,
        "image":          None,
        "in_stock":       None,
        "stock_label":    None,
        "pincode":        req.pincode,
        "pincode_result": None,
        "platform":       None,
        "last_checked":   None,
        "active":         True,
    }
    watchlist[item_id] = item
    asyncio.create_task(_watch_loop(item_id))
    await ws_manager.broadcast({"type": "watchlist_add", "data": item})
    return item

@app.delete("/api/watchlist/{item_id}")
async def remove_watchlist(item_id: str):
    if item_id not in watchlist:
        raise HTTPException(404, "Not found")
    watchlist[item_id]["active"] = False
    del watchlist[item_id]
    await ws_manager.broadcast({"type": "watchlist_remove", "data": {"id": item_id}})
    return {"ok": True}

@app.get("/api/settings")
async def get_settings():
    """Return settings, masking the token for display."""
    safe = {**settings}
    if safe["telegram_token"]:
        safe["telegram_token"] = "••••" + safe["telegram_token"][-4:]
    return safe

@app.post("/api/settings")
async def update_settings(req: SettingsReq):
    """
    Update and immediately persist settings to settings.json.
    Sending an empty string for telegram_token clears it.
    Omitting a field (None) leaves it unchanged.
    """
    if req.telegram_token is not None:
        settings["telegram_token"] = req.telegram_token
        # Auto-enable notifications when a token is provided
        if req.telegram_token and settings["telegram_chat_id"]:
            settings["notifications_enabled"] = True
        # Auto-disable when token is cleared
        if not req.telegram_token:
            settings["notifications_enabled"] = False
    if req.telegram_chat_id is not None:
        settings["telegram_chat_id"] = req.telegram_chat_id
    if req.check_interval is not None:
        settings["check_interval"] = req.check_interval
    if req.notifications_enabled is not None:
        settings["notifications_enabled"] = req.notifications_enabled

    _save_settings(settings)
    return {"ok": True}

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    await ws.send_json({
        "type": "init",
        "data": {
            "watchlist": list(watchlist.values()),
            "history":   history[:50],
        },
    })
    try:
        while True:
            await ws.receive_text()  # keep-alive ping
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)

# ─── Background watchlist loop ────────────────────────────────────────────────
async def _watch_loop(item_id: str):
    while True:
        item = watchlist.get(item_id)
        if not item or not item.get("active", True):
            return

        item["status"] = "checking"
        await ws_manager.broadcast({"type": "watchlist_update", "data": item})

        result = await monitor.check_once(item["url"], pincode=item.get("pincode"))

        item = watchlist.get(item_id)
        if not item:
            return

        item.update({
            "status":         "active",
            "title":          result.get("title") or item["label"],
            "price":          result.get("price"),
            "image":          result.get("image"),
            "in_stock":       result.get("in_stock"),
            "stock_label":    result.get("stock_label"),
            "pincode_result": result.get("pincode_result"),
            "platform":       result.get("platform"),
            "last_checked":   datetime.now().isoformat(),
        })
        await ws_manager.broadcast({"type": "watchlist_update", "data": item})
        await _maybe_notify(result)

        await asyncio.sleep(item.get("interval", 30))

# ─── Static frontend ──────────────────────────────────────────────────────────
FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="static")
