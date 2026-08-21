from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
import sqlite3
import database
import ntfy_client

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
    location: str | None = None

class AlertSignup(BaseModel):
    name: str
    email: EmailStr

class UpdateStatus(BaseModel):
    pin: str
    request_id: int
    new_status: str

def trigger_mass_alert(subject: str, message: str, ntfy_title: str = "ARC Van update",
                       ntfy_emoji: str = "driver", ntfy_priority: str = "default",
                       location: str | None = None):
    conn = sqlite3.connect(database.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM users")
    recipients = [row[0] for row in cursor.fetchall()]
    conn.close()
    try:
        print(f"\n📢 [MASS ALERT SENT TO {len(recipients)} REGISTERED STUDENTS]")
    except UnicodeEncodeError:
        print(f"[MASS ALERT SENT TO {len(recipients)} REGISTERED STUDENTS]")
    print(f"Subject: {subject}\nMessage: {message}\n" + "-" * 40)
    # Push the same alert to the ntfy students topic so phones light up.
    ntfy_client.notify_students(ntfy_title, message, emoji=ntfy_emoji,
                                priority=ntfy_priority)

@app.get("/api/alerts/latest")
def latest_alert():
    return database.get_latest_alert() or {"id": 0, "title": "No new alerts", "detail": "", "location": None, "created_at": ""}

@app.get("/api/ntfy/config")
def ntfy_config():
    """Return the ntfy topics + subscribe URLs so the UI can show them."""
    return {
        "students": {"topic": ntfy_client.students_topic(), "url": ntfy_client.students_subscribe_url()},
        "driver": {"topic": ntfy_client.driver_topic(), "url": ntfy_client.driver_subscribe_url()},
    }


@app.post("/api/alerts/signup")
def signup_for_alerts(signup: AlertSignup):
    conn = sqlite3.connect(database.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (email) VALUES (?)", (signup.email.lower(),))
    conn.commit()
    conn.close()
    # Tell the driver a new student just subscribed.
    ntfy_client.notify_driver("New student signed up",
                              f"{signup.name} signed up for 045/048 Van alerts.",
                              emoji="signup")
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
    # Let the driver know a ride request just came in.
    ntfy_client.notify_driver("New ride request",
                              f"Pickup: {req.pickup}  ->  Dropoff: {req.dropoff}  ({assigned_status})",
                              emoji="ride")
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
    # Alert the driver that a student is walking to the van now.
    ntfy_client.notify_driver("Student heading to the Van",
                              f"{signup.name} is on the way to the 045/048 Van.",
                              emoji="heading", priority="high")
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
    title = alert.title or "ARC Van update"
    database.save_alert(title, body, alert.location)
    # Pick an emoji/priority based on the alert title for nicer notifications.
    emoji, priority = "driver", "default"
    low = (title or "").lower()
    if "depart" in low:
        emoji, priority = "departure", "default"
    elif "full" in low:
        emoji, priority = "full", "default"
    elif "no ride" in low or "no rides" in low or "not available" in low:
        emoji, priority = "norides", "default"
    elif "at " in low or "location" in low:
        emoji, priority = "location", "default"
    bg.add_task(trigger_mass_alert, subject, body, ntfy_title=title,
                ntfy_emoji=emoji, ntfy_priority=priority, location=alert.location)
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