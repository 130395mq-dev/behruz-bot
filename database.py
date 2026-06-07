import sqlite3
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=5))

def now():
    return datetime.now(TZ)

DB_NAME = "barbershop.db"

def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS work_days (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            is_holiday INTEGER DEFAULT 0,
            FOREIGN KEY (worker_id) REFERENCES workers(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            service_name TEXT NOT NULL,
            price INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (worker_id) REFERENCES workers(id)
        )
    """)

    conn.commit()
    conn.close()

# --- WORKERS ---

def add_worker(telegram_id: int, name: str):
    conn = get_conn()
    try:
        conn.execute("INSERT INTO workers (telegram_id, name) VALUES (?, ?)", (telegram_id, name))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_worker(telegram_id: int):
    conn = get_conn()
    conn.execute("UPDATE workers SET is_active = 0 WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()

def get_worker(telegram_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM workers WHERE telegram_id = ? AND is_active = 1", (telegram_id,)).fetchone()
    conn.close()
    return row

def get_all_workers():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM workers WHERE is_active = 1").fetchall()
    conn.close()
    return rows

# --- WORK DAYS ---

def start_work_day(worker_id: int):
    conn = get_conn()
    today = now().strftime("%Y-%m-%d")
    now = now().strftime("%H:%M")
    existing = conn.execute(
        "SELECT * FROM work_days WHERE worker_id = ? AND date = ?", (worker_id, today)
    ).fetchone()
    if existing:
        conn.close()
        return False
    conn.execute(
        "INSERT INTO work_days (worker_id, date, start_time) VALUES (?, ?, ?)",
        (worker_id, today, now)
    )
    conn.commit()
    conn.close()
    return True

def end_work_day(worker_id: int):
    conn = get_conn()
    today = now().strftime("%Y-%m-%d")
    now = now().strftime("%H:%M")
    row = conn.execute(
        "SELECT * FROM work_days WHERE worker_id = ? AND date = ?", (worker_id, today)
    ).fetchone()
    if not row:
        conn.close()
        return None
    if row["end_time"]:
        conn.close()
        return None
    conn.execute(
        "UPDATE work_days SET end_time = ? WHERE worker_id = ? AND date = ?",
        (now, worker_id, today)
    )
    conn.commit()
    conn.close()
    return {"start": row["start_time"], "end": now}

def get_work_day(worker_id: int, date: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM work_days WHERE worker_id = ? AND date = ?", (worker_id, date)
    ).fetchone()
    conn.close()
    return row

def set_holiday(date: str):
    conn = get_conn()
    workers = conn.execute("SELECT id FROM workers WHERE is_active = 1").fetchall()
    for w in workers:
        existing = conn.execute(
            "SELECT * FROM work_days WHERE worker_id = ? AND date = ?", (w["id"], date)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO work_days (worker_id, date, is_holiday) VALUES (?, ?, 1)",
                (w["id"], date)
            )
    conn.commit()
    conn.close()

def workers_not_started():
    conn = get_conn()
    today = now().strftime("%Y-%m-%d")
    started_ids = [
        r["worker_id"] for r in conn.execute(
            "SELECT worker_id FROM work_days WHERE date = ? AND start_time IS NOT NULL", (today,)
        ).fetchall()
    ]
    all_workers = conn.execute("SELECT * FROM workers WHERE is_active = 1").fetchall()
    conn.close()
    return [w for w in all_workers if w["id"] not in started_ids]

def workers_not_ended():
    conn = get_conn()
    today = now().strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT w.* FROM workers w JOIN work_days wd ON w.id = wd.worker_id "
        "WHERE wd.date = ? AND wd.start_time IS NOT NULL AND wd.end_time IS NULL AND w.is_active = 1",
        (today,)
    ).fetchall()
    conn.close()
    return rows

# --- SERVICES ---

SERVICE_NAMES = [
    "✂️ Soch olish",
    "🚿 Soch yuvish",
    "🪒 Soqol olish",
    "👰 Kiyov tayyorlash",
    "💆 Yuz tozalash",
    "🎭 Maska",
    "🎨 Soch bo'yash",
]

def add_service(worker_id: int, service_name: str, price: int):
    conn = get_conn()
    today = now().strftime("%Y-%m-%d")
    now = now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO services (worker_id, date, service_name, price, created_at) VALUES (?, ?, ?, ?, ?)",
        (worker_id, today, service_name, price, now)
    )
    conn.commit()
    conn.close()

def delete_last_service(worker_id: int):
    conn = get_conn()
    today = now().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT id FROM services WHERE worker_id = ? AND date = ? ORDER BY id DESC LIMIT 1",
        (worker_id, today)
    ).fetchone()
    if row:
        conn.execute("DELETE FROM services WHERE id = ?", (row["id"],))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def get_services_by_worker_date(worker_id: int, date: str):
    conn = get_conn()
    rows = conn.execute(
        "SELECT service_name, COUNT(*) as cnt, SUM(price) as total "
        "FROM services WHERE worker_id = ? AND date = ? GROUP BY service_name",
        (worker_id, date)
    ).fetchall()
    conn.close()
    return rows

def get_services_by_worker_range(worker_id: int, days: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT date, service_name, COUNT(*) as cnt, SUM(price) as total "
        "FROM services WHERE worker_id = ? "
        "AND date >= date('now', ? || ' days') "
        "GROUP BY date, service_name ORDER BY date DESC",
        (worker_id, f"-{days-1}")
    ).fetchall()
    conn.close()
    return rows

def get_worker_summary_range(worker_id: int, days: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT date, SUM(price) as total FROM services WHERE worker_id = ? "
        "AND date >= date('now', ? || ' days') GROUP BY date ORDER BY date DESC",
        (worker_id, f"-{days-1}")
    ).fetchall()
    conn.close()
    return rows

def get_all_workers_summary_range(days: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT w.id, w.name, w.telegram_id, SUM(s.price) as total "
        "FROM workers w LEFT JOIN services s ON w.id = s.worker_id "
        "AND s.date >= date('now', ? || ' days') "
        "WHERE w.is_active = 1 GROUP BY w.id ORDER BY total DESC",
        (f"-{days-1}",)
    ).fetchall()
    conn.close()
    return rows

def get_today_summary_all():
    conn = get_conn()
    today = now().strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT w.id, w.name, w.telegram_id, "
        "wd.start_time, wd.end_time, "
        "COALESCE(SUM(s.price), 0) as total "
        "FROM workers w "
        "LEFT JOIN work_days wd ON w.id = wd.worker_id AND wd.date = ? "
        "LEFT JOIN services s ON w.id = s.worker_id AND s.date = ? "
        "WHERE w.is_active = 1 GROUP BY w.id",
        (today, today)
    ).fetchall()
    conn.close()
    return rows
