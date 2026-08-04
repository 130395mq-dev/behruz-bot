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
            is_active INTEGER DEFAULT 1,
            business TEXT DEFAULT 'barbershop'
        )
    """)
    # Add business column if not exists (for existing databases)
    try:
        c.execute("ALTER TABLE workers ADD COLUMN business TEXT DEFAULT 'barbershop'")
        conn.commit()
    except:
        conn.rollback()

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
        CREATE TABLE IF NOT EXISTS appointments (
            id SERIAL PRIMARY KEY,
            worker_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            client_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (worker_id) REFERENCES workers(id)
        )
    """)

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

    # ── AMORIA BAR — foto zona band qilish (kelin-kuyov) ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS amoria_bookings (
            id SERIAL PRIMARY KEY,
            worker_id INTEGER,
            client_name TEXT NOT NULL,
            phone TEXT,
            date TEXT NOT NULL,
            price INTEGER NOT NULL DEFAULT 0,
            deposit INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # ── AMORIA BAR — disko bar kunlik tushum ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS amoria_disco (
            id SERIAL PRIMARY KEY,
            worker_id INTEGER,
            date TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # ── KELIN LIBOSI / IMPERIUM — kiyim savdolari ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS dress_sales (
            id SERIAL PRIMARY KEY,
            business TEXT NOT NULL,
            worker_id INTEGER,
            date TEXT NOT NULL,
            price INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

def dict_row(cursor, row):
    cols = [desc[0] for desc in cursor.description]
    return dict(zip(cols, row))

BUSINESS_TITLES = {
    "barbershop": "💈 Barbershop",
    "amoria_bar": "🍸 Amoria Bar",
    "amoria_dress": "👰 Amoria kelin libosi",
    "imperium": "🏛 Imperium",
}

def worker_exists_message(telegram_id: int) -> str:
    """Xodim qo'shib bo'lmaganda sababini tushuntiruvchi xabar."""
    w = get_worker(telegram_id)
    if w:
        biz = BUSINESS_TITLES.get(w.get("business") or "barbershop", "boshqa biznes")
        return (f"⚠️ Bu ID allaqachon {biz} da faol xodim: {w['name']}.\n"
                f"Boshqa biznesga o'tkazish uchun avval o'sha biznesdan o'chiring.")
    return "⚠️ Bu ID allaqachon mavjud."

# --- WORKERS ---

def add_worker(telegram_id: int, name: str, business: str = "barbershop"):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT is_active FROM workers WHERE telegram_id = %s", (telegram_id,))
        row = c.fetchone()
        if row:
            if row[0] == 1:
                return False  # faol xodim sifatida allaqachon mavjud
            # o'chirilgan xodim — qayta faollashtiramiz
            c.execute(
                "UPDATE workers SET is_active = 1, name = %s, business = %s WHERE telegram_id = %s",
                (name, business, telegram_id)
            )
            conn.commit()
            return True
        c.execute("INSERT INTO workers (telegram_id, name, business) VALUES (%s, %s, %s)", (telegram_id, name, business))
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        conn.rollback()
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

def get_all_workers(business: str = "barbershop"):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM workers WHERE is_active = 1 AND COALESCE(business, 'barbershop') = %s", (business,))
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
    c.execute("SELECT id FROM workers WHERE is_active = 1 AND COALESCE(business, 'barbershop') = 'barbershop'")
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
    c.execute("SELECT * FROM workers WHERE is_active = 1 AND COALESCE(business, 'barbershop') = 'barbershop'")
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
        "WHERE wd.date = %s AND wd.start_time IS NOT NULL AND wd.end_time IS NULL AND w.is_active = 1 "
        "AND COALESCE(w.business, 'barbershop') = 'barbershop'",
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
        "AND date::date >= CURRENT_DATE - INTERVAL '1 day' * %s "
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
        "AND date::date >= CURRENT_DATE - INTERVAL '1 day' * %s GROUP BY date ORDER BY date DESC",
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
        "AND s.date::date >= CURRENT_DATE - INTERVAL '1 day' * %s "
        "WHERE w.is_active = 1 AND COALESCE(w.business, 'barbershop') = 'barbershop' "
        "GROUP BY w.id, w.name, w.telegram_id ORDER BY total DESC",
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
        "WHERE w.is_active = 1 AND COALESCE(w.business, 'barbershop') = 'barbershop' "
        "GROUP BY w.id, w.name, w.telegram_id, wd.start_time, wd.end_time",
        (today, today)
    )
    rows = c.fetchall()
    result = [dict_row(c, r) for r in rows]
    conn.close()
    return result


# --- APPOINTMENTS ---

def add_appointment(worker_id: int, date: str, time: str, client_name: str):
    conn = get_conn()
    now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
    c = conn.cursor()
    c.execute(
        "INSERT INTO appointments (worker_id, date, time, client_name, created_at) VALUES (%s, %s, %s, %s, %s)",
        (worker_id, date, time, client_name, now_str)
    )
    conn.commit()
    conn.close()

def get_appointments(worker_id: int, date: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id, time, client_name FROM appointments WHERE worker_id = %s AND date = %s ORDER BY time",
        (worker_id, date)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_appointments(date: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT a.id, w.name, a.time, a.client_name FROM appointments a "
        "JOIN workers w ON a.worker_id = w.id "
        "WHERE a.date = %s ORDER BY a.time",
        (date,)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def delete_appointment(appointment_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM appointments WHERE id = %s", (appointment_id,))
    conn.commit()
    conn.close()


# ─── AMORIA BAR ───

def get_amoria_workers():
    return get_all_workers("amoria_bar")

# --- Foto zona band qilish ---

def add_amoria_booking(worker_id, client_name, phone, date, price, deposit):
    conn = get_conn()
    now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
    c = conn.cursor()
    c.execute(
        "INSERT INTO amoria_bookings (worker_id, client_name, phone, date, price, deposit, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (worker_id, client_name, phone, date, price, deposit, now_str)
    )
    bid = c.fetchone()[0]
    conn.commit()
    conn.close()
    return bid

def get_amoria_booking(booking_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM amoria_bookings WHERE id = %s", (booking_id,))
    row = c.fetchone()
    result = dict_row(c, row) if row else None
    conn.close()
    return result

def delete_amoria_booking(booking_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM amoria_bookings WHERE id = %s", (booking_id,))
    conn.commit()
    conn.close()

def get_amoria_bookings_range(date_from, date_to):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM amoria_bookings WHERE date BETWEEN %s AND %s ORDER BY date, id",
        (date_from, date_to)
    )
    rows = c.fetchall()
    result = [dict_row(c, r) for r in rows]
    conn.close()
    return result

def get_amoria_bookings_upcoming(from_date):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM amoria_bookings WHERE date >= %s ORDER BY date, id",
        (from_date,)
    )
    rows = c.fetchall()
    result = [dict_row(c, r) for r in rows]
    conn.close()
    return result

# --- Disko bar kunlik tushum ---

def add_amoria_disco(worker_id, date, amount):
    conn = get_conn()
    now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
    c = conn.cursor()
    c.execute(
        "INSERT INTO amoria_disco (worker_id, date, amount, created_at) VALUES (%s, %s, %s, %s)",
        (worker_id, date, amount, now_str)
    )
    conn.commit()
    conn.close()

def get_amoria_disco_range(date_from, date_to):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT date, SUM(amount) as total FROM amoria_disco "
        "WHERE date BETWEEN %s AND %s GROUP BY date ORDER BY date",
        (date_from, date_to)
    )
    rows = c.fetchall()
    result = [dict_row(c, r) for r in rows]
    conn.close()
    return result

# ─── KELIN LIBOSI / IMPERIUM — kiyim savdolari ───

def add_dress_sale(business, worker_id, date, price):
    conn = get_conn()
    now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
    c = conn.cursor()
    c.execute(
        "INSERT INTO dress_sales (business, worker_id, date, price, created_at) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (business, worker_id, date, price, now_str)
    )
    sid = c.fetchone()[0]
    conn.commit()
    conn.close()
    return sid

def get_dress_sale(sale_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM dress_sales WHERE id = %s", (sale_id,))
    row = c.fetchone()
    result = dict_row(c, row) if row else None
    conn.close()
    return result

def delete_dress_sale(sale_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM dress_sales WHERE id = %s", (sale_id,))
    conn.commit()
    conn.close()

def get_dress_sales_range(business, date_from, date_to):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT ds.*, w.name as worker_name FROM dress_sales ds "
        "LEFT JOIN workers w ON ds.worker_id = w.id "
        "WHERE ds.business = %s AND ds.date BETWEEN %s AND %s ORDER BY ds.date, ds.id",
        (business, date_from, date_to)
    )
    rows = c.fetchall()
    result = [dict_row(c, r) for r in rows]
    conn.close()
    return result

def get_dress_sales_by_worker(business, worker_id, limit=10):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM dress_sales WHERE business = %s AND worker_id = %s "
        "ORDER BY id DESC LIMIT %s",
        (business, worker_id, limit)
    )
    rows = c.fetchall()
    result = [dict_row(c, r) for r in rows]
    conn.close()
    return result

def delete_last_amoria_disco(worker_id, date):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM amoria_disco WHERE worker_id = %s AND date = %s ORDER BY id DESC LIMIT 1", (worker_id, date))
    row = c.fetchone()
    if row:
        c.execute("DELETE FROM amoria_disco WHERE id = %s", (row[0],))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False
