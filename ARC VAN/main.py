import os
import json
from typing import List
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx

import database

app = FastAPI(title="ARC Class 045/048 Shuttle")
database.init_db()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DRIVER_PIN = "045048"
MAX_CAPACITY = 15

# --- TELEGRAM CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8760268822:AAHBjq_ckgCoZQ1cYybg6Us25A4X-PSTIOs")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "@YOUR_CHANNEL_USERNAME")

ACTIVE_POC = database.get_driver_poc()

async def send_telegram_alert(text: str) -> dict:
    """Direct broadcast to Telegram Channel."""
    if "YOUR_CHANNEL" in TELEGRAM_CHAT_ID:
        print("⚠️ Telegram channel username not set yet.")
        return {"success": False, "status": 400, "detail": "Missing Telegram Channel @username"}

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        async with httpx.AsyncClient(verify=False, timeout=8.0) as client:
            resp = await client.post(url, json=payload)
            print(f"🚀 [TELEGRAM ALERT] HTTP {resp.status_code}")
            return {"success": resp.status_code == 200, "status": resp.status_code, "detail": resp.text}
    except Exception as e:
        print(f"❌ [TELEGRAM ERROR]: {e}")
        return {"success": False, "status": 500, "detail": str(e)}

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        payload = json.dumps(message)
        dead = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(payload)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)

manager = ConnectionManager()

# --- Data Models with PIN Protection ---
class PinVerifyPayload(BaseModel):
    pin: str

class DriverPOCPayload(BaseModel):
    pin: str
    driver_name: str | None = ""
    contact_info: str | None = ""

class AlertPayload(BaseModel):
    pin: str
    current_stop: str | None = "Van Route"
    next_stop: str | None = "Van Route"
    eta_mins: int | None = 0
    title: str | None = None
    detail: str | None = None
    location: str | None = None

class RideRequest(BaseModel):
    name: str
    contact: str | None = ""
    pickup: str
    dropoff: str

class WalkerPayload(BaseModel):
    name: str
    contact: str | None = ""

class CompleteRequestPayload(BaseModel):
    pin: str
    request_id: int

class RemoveWalkerPayload(BaseModel):
    pin: str
    walker_id: int

class UpdateStatus(BaseModel):
    pin: str
    request_id: int | None = 0
    new_status: str | None = ""

class DriverRequestQuery(BaseModel):
    pin: str

class TestTelegramPayload(BaseModel):
    pin: str

@app.websocket("/ws/alerts")
async def websocket_alerts_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "PING":
                    await websocket.send_text(json.dumps({"type": "PONG"}))
            except Exception:
                pass
    except (WebSocketDisconnect, Exception):
        manager.disconnect(websocket)

@app.get("/healthz")
def health():
    return {"status": "healthy"}

@app.post("/api/test-telegram")
async def test_telegram(payload: TestTelegramPayload):
    if payload.pin != DRIVER_PIN:
        raise HTTPException(status_code=403, detail="Invalid Driver PIN")
    msg = "🔔 <b>ARC Shuttle Diagnostic Test</b>\n\nTelegram notifications are fully connected and active!"
    res = await send_telegram_alert(msg)
    return res

@app.post("/api/driver/verify-pin")
def verify_driver_pin(payload: PinVerifyPayload):
    if payload.pin == DRIVER_PIN:
        return {"success": True, "token": "driver-authenticated-session"}
    raise HTTPException(status_code=401, detail="Invalid PIN")

@app.get("/api/driver/poc")
def get_poc():
    global ACTIVE_POC
    return ACTIVE_POC

@app.post("/api/driver/poc")
async def set_poc(payload: DriverPOCPayload):
    global ACTIVE_POC
    if payload.pin != DRIVER_PIN:
        raise HTTPException(status_code=403, detail="Invalid Driver PIN")

    d_name = (payload.driver_name or "").strip()
    c_info = (payload.contact_info or "").strip()
    
    database.save_driver_poc(d_name, c_info)
    ACTIVE_POC = {"driver_name": d_name, "contact_info": c_info, "updated_at": "Just now"}
    
    if d_name:
        await send_telegram_alert(f"🪪 <b>Duty Driver Updated</b>\n\n<b>Driver:</b> {d_name}\n<b>Contact:</b> {c_info or 'N/A'}")
    else:
        await send_telegram_alert("ℹ️ <b>Duty Driver Contact Cleared</b>")

    await manager.broadcast({
        "type": "POC_UPDATED",
        "poc": ACTIVE_POC
    })
    return {"success": True, "poc": ACTIVE_POC}

@app.get("/api/alerts/latest")
def latest_alert():
    return database.get_latest_alert() or {"id": 0, "title": "No new alerts", "detail": "", "location": None, "created_at": ""}

@app.get("/api/status")
def get_status():
    global ACTIVE_POC
    status = database.get_queue_data()
    status["walkers"] = database.get_walking_list()
    status["walking_count"] = len(status["walkers"])
    status["poc"] = ACTIVE_POC
    return status

@app.post("/api/driver/broadcast")
async def broadcast_alert(alert: AlertPayload):
    if alert.pin != DRIVER_PIN:
        raise HTTPException(status_code=403, detail="Invalid Driver PIN")

    loc = alert.location or alert.current_stop
    subject = alert.title or f"Van Location: {loc}"
    body = alert.detail or f"045/048 Van is currently at {loc}."

    database.clear_requests_at_location(loc)
    alert_id = database.save_alert(subject, body, loc)
    latest = database.get_latest_alert()
    queue_data = database.get_queue_data()

    await send_telegram_alert(f"🚐 <b>{subject}</b>\n\n{body}")

    await manager.broadcast({
        "type": "NEW_ALERT",
        "alert": latest or {"id": alert_id, "title": subject, "detail": body, "location": loc, "created_at": "Just now"}
    })
    await manager.broadcast({
        "type": "REQUESTS_UPDATED",
        "requests": queue_data["manifest"]
    })

    return {"success": True}

@app.post("/api/driver/requests")
def driver_requests(payload: DriverRequestQuery):
    global ACTIVE_POC
    if payload.pin != DRIVER_PIN:
        raise HTTPException(status_code=403, detail="Invalid Driver PIN")
    return {
        "requests": database.get_queue_data()["manifest"],
        "walkers": database.get_walking_list(),
        "poc": ACTIVE_POC
    }

@app.post("/api/driver/complete-request")
async def complete_request(payload: CompleteRequestPayload):
    if payload.pin != DRIVER_PIN:
        raise HTTPException(status_code=403, detail="Invalid Driver PIN")
    database.complete_single_request(payload.request_id)
    queue_data = database.get_queue_data()
    await manager.broadcast({
        "type": "REQUESTS_UPDATED",
        "requests": queue_data["manifest"]
    })
    return {"success": True}

@app.post("/api/driver/remove-walker")
async def remove_walker(payload: RemoveWalkerPayload):
    if payload.pin != DRIVER_PIN:
        raise HTTPException(status_code=403, detail="Invalid Driver PIN")
    database.remove_single_walker(payload.walker_id)
    walkers = database.get_walking_list()
    await manager.broadcast({
        "type": "WALKERS_UPDATED",
        "walkers": walkers,
        "count": len(walkers)
    })
    return {"success": True}

@app.post("/api/request-ride")
async def request_ride(req: RideRequest):
    queue_info = database.get_queue_data()
    assigned_status = "CONFIRMED" if queue_info["active_count"] < MAX_CAPACITY else "WAITLIST"

    database.add_ride_request(
        name=req.name.strip(),
        contact=(req.contact or '').strip(),
        pickup=req.pickup.strip(),
        dropoff=req.dropoff.strip(),
        status=assigned_status
    )

    contact_text = f"\n<b>Contact:</b> {req.contact.strip()}" if req.contact else ""
    await send_telegram_alert(f"🚖 <b>New Ride Request</b>\n\n<b>Rider:</b> {req.name.strip()}\n<b>Pickup:</b> {req.pickup.strip()} ➔ <b>Dropoff:</b> {req.dropoff.strip()}{contact_text}")

    queue_data = database.get_queue_data()
    await manager.broadcast({
        "type": "NEW_RIDE_REQUEST",
        "name": req.name,
        "contact": req.contact or "",
        "pickup": req.pickup,
        "dropoff": req.dropoff,
        "status": assigned_status
    })
    await manager.broadcast({
        "type": "REQUESTS_UPDATED",
        "requests": queue_data["manifest"]
    })

    return {"status": assigned_status}

@app.post("/api/student/heading-to-van")
async def heading_to_van(payload: WalkerPayload):
    database.add_active_walker(
        name=payload.name.strip(),
        contact=(payload.contact or '').strip()
    )

    contact_text = f"\n<b>Contact:</b> {payload.contact.strip()}" if payload.contact else ""
    await send_telegram_alert(f"🚶 <b>Incoming Passenger</b>\n\n{payload.name.strip()} is walking to the van pickup spot right now!{contact_text}")

    walkers = database.get_walking_list()
    await manager.broadcast({
        "type": "WALKERS_UPDATED",
        "walkers": walkers,
        "count": len(walkers),
        "new_name": payload.name,
        "new_contact": payload.contact or ""
    })
    return {"success": True, "count": len(walkers)}

@app.post("/api/driver/clear-walking")
async def clear_walking(payload: UpdateStatus):
    if payload.pin != DRIVER_PIN:
        raise HTTPException(status_code=403, detail="Invalid Driver PIN")
    database.clear_walking_to_van()
    await manager.broadcast({"type": "WALKERS_UPDATED", "walkers": [], "count": 0})
    return {"success": True}

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/style.css")
def serve_css():
    return FileResponse(os.path.join(BASE_DIR, "style.css"))

@app.get("/app.js")
def serve_js():
    return FileResponse(os.path.join(BASE_DIR, "app.js"))
