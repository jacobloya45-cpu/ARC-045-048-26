import os
import sqlite3
import json
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
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                dead_connections.append(connection)
        for dead in dead_connections:
            self.disconnect(dead)

manager = ConnectionManager()

class PinVerifyPayload(BaseModel):
    pin: str

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
    email: str | None = None
    pickup: str
    dropoff: str

class AlertSignup(BaseModel):
    name: str
    email: str

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

@app.websocket("/ws/alerts")
async def websocket_alerts_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                parsed = json.loads(data)
                if parsed.get("type") == "PING":
                    await websocket.send_text(json.dumps({"type": "PONG"}))
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

@app.get("/healthz")
def health():
    return {"status": "healthy"}

@app.post("/api/driver/verify-pin")
def verify_driver_pin(payload: PinVerifyPayload):
    if payload.pin == DRIVER_PIN:
        return {"success": True, "token": "driver-authenticated-session"}
    raise HTTPException(status_code=401, detail="Invalid PIN")

@app.get("/api/alerts/latest")
def latest_alert():
    return database.get_latest_alert() or {"id": 0, "title": "No new alerts", "detail": "", "location": None, "created_at": ""}

@app.get("/api/status")
def get_status():
    status = database.get_queue_data()
    status["walkers"] = database.get_walking_list()
    status["walking_count"] = len(status["walkers"])
    return status

@app.post("/api/driver/broadcast")
async def broadcast_alert(alert: AlertPayload):
    if alert.pin != DRIVER_PIN:
        raise HTTPException(status_code=403, detail="Invalid Driver PIN")

    loc = alert.location or alert.current_stop
    subject = alert.title or f"🚐 Van Location: {loc}"
    body = alert.detail or f"045/048 Van is currently at {loc}."

    database.clear_requests_at_location(loc)
    alert_id = database.save_alert(subject, body, loc)
    latest = database.get_latest_alert()
    queue_data = database.get_queue_data()

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
    if payload.pin != DRIVER_PIN:
        raise HTTPException(status_code=403, detail="Invalid Driver PIN")
    return {
        "requests": database.get_queue_data()["manifest"],
        "walkers": database.get_walking_list()
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
    conn = sqlite3.connect(database.DB_NAME)
    cursor = conn.cursor()
    request_email = req.email or f"ride-{os.urandom(4).hex()}@arc-van.local"
    
    cursor.execute("INSERT OR REPLACE INTO users (name, email) VALUES (?, ?)", (req.name, request_email.lower()))
    cursor.execute("SELECT id FROM users WHERE email = ?", (request_email.lower(),))
    user_id = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM requests WHERE status IN ('CONFIRMED', 'BOARDED')")
    active_count = cursor.fetchone()[0]
    assigned_status = "CONFIRMED" if active_count < MAX_CAPACITY else "WAITLIST"

    cursor.execute(
        "INSERT INTO requests (user_id, pickup, dropoff, status) VALUES (?, ?, ?, ?)",
        (user_id, req.pickup, req.dropoff, assigned_status)
    )
    conn.commit()
    conn.close()

    queue_data = database.get_queue_data()
    await manager.broadcast({
        "type": "NEW_RIDE_REQUEST",
        "name": req.name,
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
async def heading_to_van(signup: AlertSignup):
    conn = sqlite3.connect(database.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (name, email) VALUES (?, ?)", (signup.name, signup.email.lower()))
    conn.commit()
    cursor.execute("SELECT id FROM users WHERE email = ?", (signup.email.lower(),))
    user_id = cursor.fetchone()[0]
    cursor.execute("INSERT INTO walking_to_van (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

    walkers = database.get_walking_list()
    await manager.broadcast({
        "type": "WALKERS_UPDATED",
        "walkers": walkers,
        "count": len(walkers),
        "new_name": signup.name
    })
    return {"success": True}

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
