import sqlite3

DB_NAME = "shuttle.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Standalone requests table with embedded contact details
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ride_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            contact_info TEXT DEFAULT '',
            pickup TEXT NOT NULL,
            dropoff TEXT NOT NULL,
            status TEXT DEFAULT 'CONFIRMED',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Standalone active walkers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_walkers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            contact_info TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Alerts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            detail TEXT NOT NULL,
            location TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Driver POC table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS driver_poc (
            id INTEGER PRIMARY KEY,
            driver_name TEXT,
            contact_info TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM driver_poc WHERE id = 1")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO driver_poc (id, driver_name, contact_info) VALUES (1, '', '')")

    conn.commit()
    conn.close()

def save_driver_poc(driver_name: str, contact_info: str):
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE driver_poc SET driver_name = ?, contact_info = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1", (driver_name, contact_info))
    if cursor.rowcount == 0:
        cursor.execute("INSERT INTO driver_poc (id, driver_name, contact_info) VALUES (1, ?, ?)", (driver_name, contact_info))
    conn.commit()
    conn.close()

def get_driver_poc():
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT driver_name, contact_info, updated_at FROM driver_poc WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
        if not row:
            return {"driver_name": "", "contact_info": "", "updated_at": ""}
        return {"driver_name": row[0] or "", "contact_info": row[1] or "", "updated_at": row[2] or ""}
    except Exception:
        conn.close()
        return {"driver_name": "", "contact_info": "", "updated_at": ""}

def save_alert(title, detail, location=None):
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO alerts (title, detail, location) VALUES (?, ?, ?)", (title, detail, location))
    conn.commit()
    alert_id = cursor.lastrowid
    conn.close()
    return alert_id

def get_latest_alert():
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, title, detail, location, created_at FROM alerts ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {"id": row[0], "title": row[1], "detail": row[2], "location": row[3], "created_at": row[4]}
    except Exception:
        conn.close()
        return None

def add_ride_request(name: str, contact: str, pickup: str, dropoff: str, status: str = 'CONFIRMED'):
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ride_requests (student_name, contact_info, pickup, dropoff, status)
        VALUES (?, ?, ?, ?, ?)
    """, (name, contact or '', pickup, dropoff, status))
    conn.commit()
    req_id = cursor.lastrowid
    conn.close()
    return req_id

def get_queue_data():
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, student_name, contact_info, pickup, dropoff, status, created_at
            FROM ride_requests
            WHERE status IN ('CONFIRMED', 'WAITLIST', 'BOARDED')
            ORDER BY id ASC
        """)
        rows = cursor.fetchall()
    except Exception:
        rows = []
    conn.close()
    
    confirmed = [r for r in rows if r[5] in ('CONFIRMED', 'BOARDED')]
    waitlist = [r for r in rows if r[5] == 'WAITLIST']
    return {"manifest": rows, "active_count": len(confirmed), "waitlist_count": len(waitlist)}

def clear_requests_at_location(location: str):
    if not location:
        return 0
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE ride_requests 
            SET status = 'COMPLETED' 
            WHERE LOWER(TRIM(pickup)) = LOWER(TRIM(?)) AND status IN ('CONFIRMED', 'WAITLIST', 'BOARDED')
        """, (location,))
        affected = cursor.rowcount
        conn.commit()
    except Exception:
        affected = 0
    conn.close()
    return affected

def complete_single_request(request_id: int):
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE ride_requests SET status = 'COMPLETED' WHERE id = ?", (request_id,))
    conn.commit()
    conn.close()

def add_active_walker(name: str, contact: str):
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO active_walkers (student_name, contact_info) VALUES (?, ?)", (name, contact or ''))
    conn.commit()
    walker_id = cursor.lastrowid
    conn.close()
    return walker_id

def get_walking_list():
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, student_name, contact_info, created_at FROM active_walkers ORDER BY id ASC")
        rows = cursor.fetchall()
    except Exception:
        rows = []
    conn.close()
    return [{"id": r[0], "name": r[1], "contact": r[2], "time": r[3]} for r in rows]

def clear_walking_to_van():
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM active_walkers")
    conn.commit()
    conn.close()

def remove_single_walker(walker_id: int):
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM active_walkers WHERE id = ?", (walker_id,))
    conn.commit()
    conn.close()
