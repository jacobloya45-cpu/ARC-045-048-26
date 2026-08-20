from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
import sqlite3
import database

app = FastAPI(title="ARC Class 045/048 Shuttle")
database.init_db()

DRIVER_PIN = "045048"
MAX_CAPACITY = 15

class RideRequest(BaseModel):
    email: EmailStr
    pickup: str
    dropoff: str

class AlertPayload(BaseModel):
    pin: str
    current_stop: str
    next_stop: str
    eta_mins: int
    title: str | None = None
    detail: str | None = None

class AlertSignup(BaseModel):
    name: str
    email: EmailStr

class UpdateStatus(BaseModel):
    pin: str
    request_id: int
    new_status: str

def trigger_mass_alert(subject: str, message: str):
    conn = sqlite3.connect(database.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM users")
    recipients = [row[0] for row in cursor.fetchall()]
    conn.close()
    print(f"\n📢 [MASS ALERT SENT TO {len(recipients)} REGISTERED STUDENTS]")
    print(f"Subject: {subject}\nMessage: {message}\n" + "-" * 40)

@app.get("/api/alerts/latest")
def latest_alert():
    return database.get_latest_alert() or {"id": 0, "title": "No new alerts", "detail": "", "created_at": ""}

@app.post("/api/alerts/signup")
def signup_for_alerts(signup: AlertSignup):
    conn = sqlite3.connect(database.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (email) VALUES (?)", (signup.email.lower(),))
    conn.commit()
    conn.close()
    return {"success": True}

@app.get("/api/status")
def get_status():
    status = database.get_queue_data()
    status["walking_count"] = database.get_walking_count()
    return status

@app.post("/api/request-ride")
def request_ride(req: RideRequest):
    conn = sqlite3.connect(database.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (email) VALUES (?)", (req.email,))
    cursor.execute("SELECT id FROM users WHERE email = ?", (req.email,))
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
    return {"status": assigned_status}

@app.post("/api/student/heading-to-van")
def heading_to_van(signup: AlertSignup):
    conn = sqlite3.connect(database.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (email) VALUES (?)", (signup.email.lower(),))
    conn.commit()
    cursor.execute("SELECT id FROM users WHERE email = ?", (signup.email.lower(),))
    user_id = cursor.fetchone()[0]
    cursor.execute("INSERT INTO walking_to_van (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()
    return {"success": True}

@app.post("/api/driver/clear-walking")
def clear_walking(payload: UpdateStatus):
    if payload.pin != DRIVER_PIN:
        raise HTTPException(status_code=403, detail="Invalid Driver PIN")
    database.clear_walking_to_van()
    return {"success": True}

@app.post("/api/driver/broadcast")
def broadcast_alert(alert: AlertPayload, bg: BackgroundTasks):
    if alert.pin != DRIVER_PIN:
        raise HTTPException(status_code=403, detail="Invalid Driver PIN")
    subject = "ARC Van Pickup Alert"
    body = alert.detail or f"15-PAX Van is at {alert.current_stop}, departing in {alert.eta_mins} mins for {alert.next_stop}."
    database.save_alert(alert.title or "ARC Van update", body)
    bg.add_task(trigger_mass_alert, subject, body)
    return {"success": True}

@app.post("/api/driver/update-status")
def update_status(payload: UpdateStatus):
    if payload.pin != DRIVER_PIN:
        raise HTTPException(status_code=403, detail="Invalid Driver PIN")
    conn = sqlite3.connect(database.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET status = ? WHERE id = ?", (payload.new_status, payload.request_id))
    
    if payload.new_status == "DROPPED_OFF":
        cursor.execute("SELECT COUNT(*) FROM requests WHERE status IN ('CONFIRMED', 'BOARDED')")
        if cursor.fetchone()[0] < MAX_CAPACITY:
            cursor.execute("""
                UPDATE requests SET status = 'CONFIRMED' 
                WHERE id = (SELECT id FROM requests WHERE status = 'WAITLIST' ORDER BY id ASC LIMIT 1)
            """)
    conn.commit()
    conn.close()
    return {"success": True}

# Serve root HTML
@app.get("/")
def serve_index():
    return FileResponse("index.html")

@app.get("/style.css")
def serve_css():
    return FileResponse("style.css")

@app.get("/app.js")
def serve_js():
    return FileResponse("app.js")
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
import urllib.request
import urllib.parse
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()

NTFY_TOPIC = "arc-van-fortliberty-alerts"  # Change this to your chosen topic name

def send_push_notification(title: str, message: str, priority: str = "default", tags: str = "minibus"):
    """Sends a free instant push notification via ntfy.sh"""
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    headers = {
        "Title": title.encode("utf-8"),
        "Priority": priority,     # Options: min, low, default, high, urgent
        "Tags": tags              # Adds an emoji/icon (e.g., minibus, warning, round_pushpin)
    }
    req = urllib.request.Request(url, data=message.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            return response.status == 200
    except Exception as e:
        print(f"Error sending ntfy notification: {e}")
        return False

class BroadcastPayload(BaseModel):
    current_stop: str
    status_message: str

@app.post("/api/driver/broadcast")
async def driver_broadcast(payload: BroadcastPayload, x_driver_pin: str = Header(None)):
    # Verify Driver PIN
    if x_driver_pin != "045048":
        raise HTTPException(status_code=401, detail="Unauthorized Driver PIN")

    title = f"🚐 Van Update: {payload.current_stop}"
    body = payload.status_message

    success = send_push_notification(title=title, message=body, priority="high", tags="minibus,round_pushpin")
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to broadcast notification")
        
    return {"status": "success", "message": "Alert sent successfully to all riders"}
import os
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()

# 1. Health Check Endpoint for Render
@app.get("/healthz")
async def health_check():
    return {"status": "healthy"}

# 2. Base Route (Fixes the 404 error and keeps Render alive)
@app.get("/")
async def serve_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"status": "ok", "message": "Server is running"}

# 3. Serve CSS and JS assets if placed in the same folder
@app.get("/style.css")
async def serve_css():
    if os.path.exists("style.css"):
        return FileResponse("style.css", media_type="text/css")
    return FileResponse("index.html")

@app.get("/app.js")
async def serve_js():
    if os.path.exists("app.js"):
        return FileResponse("app.js", media_type="application/javascript")
    return FileResponse("index.html")
