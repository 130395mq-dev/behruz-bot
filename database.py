import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=5))

def get_now():
    return datetime.now(TZ)

def get_conn():
    url = os.getenv("DATABASE_URL")
    conn = psycopg2.connect(url)
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS work_days (
            id SERIAL PRIMARY KEY,
            worker_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            session INTEGER DEFAULT 1,
            start_time TEXT,
            end_time TEXT,
            is_holiday INTEGER DEFAULT 0,
            FOREIGN KEY (worker_id) REFERENCES workers(id)
        )
    """)
    # Add session column if not exists (for existing databases)
    try:
        c.execute("ALTER TABLE work_days ADD COLUMN session INTEGER DEFAULT 1")
        conn.commit()
    except:
        conn.rollback()

    c.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id SERIAL PRIMARY KEY,
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

def dict_row(cursor, row):
    cols = [desc[0] for desc in cursor.description]
    return dict(zip(cols, row))

# --- WORKERS ---

def add_worker(telegram_id: int, name: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO workers (telegram_id, name) VALUES (%s, %s)", (telegram_id, name))
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        return False
    finally:
        conn.close()

def remove_worker(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE workers SET is_active = 0 WHERE telegram_id = %s", (telegram_id,))
    conn.commit()
    conn.close()

def get_worker(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM workers WHERE telegram_id = %s AND is_active = 1", (telegram_id,))
    row = c.fetchone()
    result = dict_row(c, row) if row else None
    conn.close()
    return result

def get_all_workers():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM workers WHERE is_active = 1")
    rows = c.fetchall()
    result = [dict_row(c, r) for r in rows]
    conn.close()
    return result

# --- WORK DAYS ---

def start_work_day(worker_id: int, session: int = 1):
    conn = get_conn()
    today = get_now().strftime("%Y-%m-%d")
    now_time = get_now().strftime("%H:%M")
    c = conn.cursor()
    c.execute("SELECT * FROM work_days WHERE worker_id = %s AND date = %s AND session = %s", (worker_id, today, session))
    existing = c.fetchone()
    if existing:
        conn.close()
        return False
    c.execute("INSERT INTO work_days (worker_id, date, session, start_time) VALUES (%s, %s, %s, %s)", (worker_id, today, session, now_time))
    conn.commit()
    conn.close()
    return True

def get_next_session(worker_id: int):
    conn = get_conn()
    today = get_now().strftime("%Y-%m-%d")
    c = conn.cursor()
    c.execute("SELECT MAX(session) FROM work_days WHERE worker_id = %s AND date = %s", (worker_id, today))
    row = c.fetchone()
    conn.close()
    return (row[0] or 0) + 1

def allow_restart(worker_id: int):
    conn = get_conn()
    today = get_now().strftime("%Y-%m-%d")
    now_time = get_now().strftime("%H:%M")
    c = conn.cursor()
    c.execute("SELECT MAX(session) FROM work_days WHERE worker_id = %s AND date = %s", (worker_id, today))
    row = c.fetchone()
    next_session = (row[0] or 0) + 1
    c.execute("INSERT INTO work_days (worker_id, date, session, start_time) VALUES (%s, %s, %s, %s)", 
              (worker_id, today, next_session, now_time))
    conn.commit()
    conn.close()
    return next_session

def end_work_day(worker_id: int):
    conn = get_conn()
    today = get_now().strftime("%Y-%m-%d")
    now_time = get_now().strftime("%H:%M")
    c = conn.cursor()
    c.execute("SELECT * FROM work_days WHERE worker_id = %s AND date = %s ORDER BY session DESC LIMIT 1", (worker_id, today))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    row = dict_row(c, row)
    if row["end_time"]:
        conn.close()
        return None
    c.execute("UPDATE work_days SET end_time = %s WHERE worker_id = %s AND date = %s AND session = %s", 
              (now_time, worker_id, today, row["session"]))
    conn.commit()
    conn.close()
    return {"start": row["start_time"], "end": now_time}

def get_work_day(worker_id: int, date: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM work_days WHERE worker_id = %s AND date = %s ORDER BY session DESC LIMIT 1", (worker_id, date))
    row = c.fetchone()
    result = dict_row(c, row) if row else None
    conn.close()
    return result

def get_all_sessions(worker_id: int, date: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM work_days WHERE worker_id = %s AND date = %s AND is_holiday = 0 ORDER BY session", (worker_id, date))
    rows = c.fetchall()
    result = [dict_row(c, r) for r in rows]
    conn.close()
    return result

def set_holiday(date: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM workers WHERE is_active = 1")
    workers = c.fetchall()
    for w in workers:
        c.execute("SELECT * FROM work_days WHERE worker_id = %s AND date = %s", (w[0], date))
        if not c.fetchone():
            c.execute("INSERT INTO work_days (worker_id, date, is_holiday) VALUES (%s, %s, 1)", (w[0], date))
    conn.commit()
    conn.close()

def workers_not_started():
    conn = get_conn()
    today = get_now().strftime("%Y-%m-%d")
    c = conn.cursor()
    c.execute("SELECT worker_id FROM work_days WHERE date = %s AND start_time IS NOT NULL", (today,))
    started_ids = [r[0] for r in c.fetchall()]
    c.execute("SELECT * FROM workers WHERE is_active = 1")
    rows = c.fetchall()
    all_workers = [dict_row(c, r) for r in rows]
    conn.close()
    return [w for w in all_workers if w["id"] not in started_ids]

def workers_not_ended():
    conn = get_conn()
    today = get_now().strftime("%Y-%m-%d")
    c = conn.cursor()
    c.execute(
        "SELECT w.* FROM workers w JOIN work_days wd ON w.id = wd.worker_id "
        "WHERE wd.date = %s AND wd.start_time IS NOT NULL AND wd.end_time IS NULL AND w.is_active = 1",
        (today,)
    )
    rows = c.fetchall()
    result = [dict_row(c, r) for r in rows]
    conn.close()
    return result

def get_conn():
    url = os.getenv("DATABASE_URL")
    conn = psycopg2.connect(url)
    return conn

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
    today = get_now().strftime("%Y-%m-%d")
    now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
    c = conn.cursor()
    c.execute(
        "INSERT INTO services (worker_id, date, service_name, price, created_at) VALUES (%s, %s, %s, %s, %s)",
        (worker_id, today, service_name, price, now_str)
    )
    conn.commit()
    conn.close()

def delete_last_service(worker_id: int):
    conn = get_conn()
    today = get_now().strftime("%Y-%m-%d")
    c = conn.cursor()
    c.execute("SELECT id FROM services WHERE worker_id = %s AND date = %s ORDER BY id DESC LIMIT 1", (worker_id, today))
    row = c.fetchone()
    if row:
        c.execute("DELETE FROM services WHERE id = %s", (row[0],))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def get_services_by_worker_date(worker_id: int, date: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT service_name, COUNT(*) as cnt, SUM(price) as total "
        "FROM services WHERE worker_id = %s AND date = %s GROUP BY service_name",
        (worker_id, date)
    )
    rows = c.fetchall()
    result = [dict_row(c, r) for r in rows]
    conn.close()
    return result

def get_services_by_worker_range(worker_id: int, days: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT date, service_name, COUNT(*) as cnt, SUM(price) as total "
        "FROM services WHERE worker_id = %s "
        "AND date >= (CURRENT_DATE - INTERVAL '%s days')::text "
        "GROUP BY date, service_name ORDER BY date DESC",
        (worker_id, days - 1)
    )
    rows = c.fetchall()
    result = [dict_row(c, r) for r in rows]
    conn.close()
    return result

def get_worker_summary_range(worker_id: int, days: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT date, SUM(price) as total FROM services WHERE worker_id = %s "
        "AND date >= (CURRENT_DATE - INTERVAL '%s days')::text GROUP BY date ORDER BY date DESC",
        (worker_id, days - 1)
    )
    rows = c.fetchall()
    result = [dict_row(c, r) for r in rows]
    conn.close()
    return result

def get_all_workers_summary_range(days: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT w.id, w.name, w.telegram_id, COALESCE(SUM(s.price), 0) as total "
        "FROM workers w LEFT JOIN services s ON w.id = s.worker_id "
        "AND s.date >= (CURRENT_DATE - INTERVAL '%s days')::text "
        "WHERE w.is_active = 1 GROUP BY w.id, w.name, w.telegram_id ORDER BY total DESC",
        (days - 1,)
    )
    rows = c.fetchall()
    result = [dict_row(c, r) for r in rows]
    conn.close()
    return result

def get_today_summary_all():
    conn = get_conn()
    today = get_now().strftime("%Y-%m-%d")
    c = conn.cursor()
    c.execute(
        "SELECT w.id, w.name, w.telegram_id, "
        "wd.start_time, wd.end_time, "
        "COALESCE(SUM(s.price), 0) as total "
        "FROM workers w "
        "LEFT JOIN work_days wd ON w.id = wd.worker_id AND wd.date = %s "
        "LEFT JOIN services s ON w.id = s.worker_id AND s.date = %s "
        "WHERE w.is_active = 1 GROUP BY w.id, w.name, w.telegram_id, wd.start_time, wd.end_time",
        (today, today)
    )
    rows = c.fetchall()
    result = [dict_row(c, r) for r in rows]
    conn.close()
    return result
