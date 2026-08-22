import os
import json
import ssl
import asyncio
import urllib.request
import urllib.parse
from typing import List
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

import database

app = FastAPI(title="ARC Class 045/048 Shuttle")
database.init_db()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DRIVER_PIN = "045048"
MAX_CAPACITY = 15

# Single Universal Topic for ALL Driver & Student actions
NTFY_TOPIC = "arc-van-knox-045048"

ACTIVE_POC = database.get_driver_poc()

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

def sync_send_ntfy(title: str, message: str, tags: str = "minibus"):
    """
    Sends alerts to Ntfy via URL parameters.
    Bypasses all HTTP header filters and CORS restrictions.
    """
    try:
        clean_title = title.encode("ascii", "ignore").decode("ascii").strip() or "ARC Shuttle Alert"
        params = urllib.parse.urlencode({
            "title": clean_title,
            "tags": tags or "minibus",
            "priority": "urgent"
        })
        url = f"https://ntfy.sh/{NTFY_TOPIC}?{params}"
        body = (message or "ARC Shuttle update").encode("utf-8")
        
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "User-Agent": "ARC-Van/1.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5, context=ssl_ctx) as resp:
            print(f"✅ [NTFY SERVER POST {resp.status}]: {clean_title}")
            return {"success": True, "status": resp.status}
    except Exception as e:
        print(f"❌ [NTFY SERVER ERROR]: {e}")
        return {"success": False, "error": str(e)}

async def publish_ntfy(title: str, message: str, tags: str = "minibus"):
    """Dispatches in background thread without blocking the web server"""
    return await asyncio.to_thread(sync_send_ntfy, title, message, tags)

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

# --- Pydantic Data Models ---
class PinVerifyPayload(BaseModel):
    pin: str

class DriverPOCPayload(BaseModel):
    pin: str | None = "045048"
    driver_name: str | None = ""
    contact_info: str | None = ""

class AlertPayload(BaseModel):
    pin: str | None = "045048"
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
    pin: str | None = "045048"
    request_id: int

class RemoveWalkerPayload(BaseModel):
    pin: str | None = "045048"
    walker_id: int

class UpdateStatus(BaseModel):
    pin: str | None = "045048"
    request_id: int | None = 0
    new_status: str | None = ""

class DriverRequestQuery(BaseModel):
    pin: str | None = "045048"

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

@app.get("/api/test-ntfy")
async def test_ntfy():
    res = await publish_ntfy("ARC Van Test Alert", "Test push notification to ntfy.sh", "bell,white_check_mark")
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
    d_name = (payload.driver_name or "").strip()
    c_info = (payload.contact_info or "").strip()
    
    database.save_driver_poc(d_name, c_info)
    ACTIVE_POC = {"driver_name": d_name, "contact_info": c_info, "updated_at": "Just now"}
    
    if d_name:
        await publish_ntfy(
            f"Duty Driver: {d_name}",
            f"On-duty driver is {d_name}. Contact: {c_info or 'N/A'}",
            "identification_card,phone"
        )
    else:
        await publish_ntfy("Duty Driver Cleared", "Driver contact has been reset.", "heavy_minus_sign")

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
    loc = alert.location or alert.current_stop
    subject = alert.title or f"Van Location: {loc}"
    body = alert.detail or f"045/048 Van is currently at {loc}."

    database.clear_requests_at_location(loc)
    alert_id = database.save_alert(subject, body, loc)
    latest = database.get_latest_alert()
    queue_data = database.get_queue_data()

    # Publish Van Location / Departure Alert
    await publish_ntfy(subject, body, "round_pushpin,bus")

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
    return {
        "requests": database.get_queue_data()["manifest"],
        "walkers": database.get_walking_list(),
        "poc": ACTIVE_POC
    }

@app.post("/api/driver/complete-request")
async def complete_request(payload: CompleteRequestPayload):
    database.complete_single_request(payload.request_id)
    await publish_ntfy("Passenger Picked Up", f"Ride request #{payload.request_id} completed.", "white_check_mark")
    
    queue_data = database.get_queue_data()
    await manager.broadcast({
        "type": "REQUESTS_UPDATED",
        "requests": queue_data["manifest"]
    })
    return {"success": True}

@app.post("/api/driver/remove-walker")
async def remove_walker(payload: RemoveWalkerPayload):
    database.remove_single_walker(payload.walker_id)
    await publish_ntfy("Walker Arrived", "Student has boarded the van.", "white_check_mark")
    
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

    contact_text = f" ({req.contact.strip()})" if req.contact else ""
    # Push ride request notification to Ntfy
    await publish_ntfy(
        f"Ride Request: {req.name.strip()}",
        f"Pickup: {req.pickup.strip()} -> Dropoff: {req.dropoff.strip()}{contact_text}",
        "taxi,bell"
    )

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

    contact_text = f" ({payload.contact.strip()})" if payload.contact else ""
    # Push incoming walker notification to Ntfy
    await publish_ntfy(
        f"Incoming Walker: {payload.name.strip()}",
        f"{payload.name.strip()} is walking to the van now{contact_text}.",
        "walking,information_source"
    )

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
    database.clear_walking_to_van()
    await publish_ntfy("Walkers Cleared", "Driver cleared the incoming arrivals list.", "broom")
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
