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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_alert(title, detail):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO alerts (title, detail) VALUES (?, ?)", (title, detail))
    conn.commit()
    alert_id = cursor.lastrowid
    conn.close()
    return alert_id

def get_latest_alert():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, detail, created_at FROM alerts ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "title": row[1], "detail": row[2], "created_at": row[3]}

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
    