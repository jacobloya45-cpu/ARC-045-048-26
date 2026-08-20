import sqlite3

DB_NAME = "shuttle.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            pickup TEXT NOT NULL,
            dropoff TEXT NOT NULL,
            status TEXT DEFAULT 'CONFIRMED',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            detail TEXT NOT NULL,
            location TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    alert_columns = {row[1] for row in cursor.execute("PRAGMA table_info(alerts)").fetchall()}
    if "location" not in alert_columns:
        cursor.execute("ALTER TABLE alerts ADD COLUMN location TEXT")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS walking_to_van (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()

def save_alert(title, detail, location=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO alerts (title, detail, location) VALUES (?, ?, ?)", (title, detail, location))
    conn.commit()
    alert_id = cursor.lastrowid
    conn.close()
    return alert_id

def get_latest_alert():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, detail, location, created_at FROM alerts ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "title": row[1], "detail": row[2], "location": row[3], "created_at": row[4]}

def get_queue_data():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id, u.email, r.pickup, r.dropoff, r.status 
        FROM requests r
        JOIN users u ON r.user_id = u.id
        WHERE r.status IN ('CONFIRMED', 'WAITLIST', 'BOARDED')
        ORDER BY r.id ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    confirmed = [r for r in rows if r[4] in ('CONFIRMED', 'BOARDED')]
    waitlist = [r for r in rows if r[4] == 'WAITLIST']
    return {"manifest": rows, "active_count": len(confirmed), "waitlist_count": len(waitlist)}

def add_walking_to_van(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO walking_to_van (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_walking_count():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM walking_to_van")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def clear_walking_to_van():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM walking_to_van")
    conn.commit()
    conn.close()
    