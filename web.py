"""
Mini App (dashboard) uchun veb-server.
Bot bilan bitta jarayonda ishlaydi (bot.py ichida uvicorn orqali ko'tariladi).
Faqat adminlar uchun: Telegram WebApp initData imzosi tekshiriladi.
"""
import os
import hmac
import json
import hashlib
import urllib.parse
from datetime import timedelta

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse

from database import get_conn, get_now

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ADMIN_ID_2 = int(os.getenv("ADMIN_ID_2", "0"))
ADMIN_IDS = [x for x in [ADMIN_ID, ADMIN_ID_2] if x]

WEEKDAYS_UZ = ["Du", "Se", "Cho", "Pa", "Ju", "Sha", "Ya"]

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/")
def index():
    return FileResponse(
        os.path.join(BASE_DIR, "webapp", "index.html"),
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


def validate_init_data(init_data: str):
    """Telegram WebApp initData imzosini tekshiradi, user dict qaytaradi."""
    if not init_data or not BOT_TOKEN:
        return None
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received_hash):
            return None
        return json.loads(parsed.get("user", "{}"))
    except Exception:
        return None


def require_admin(init_data: str):
    user = validate_init_data(init_data)
    if not user or int(user.get("id", 0)) not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    return user


def _sum_by(c, query, params, key_idx=0, val_idx=1):
    c.execute(query, params)
    return {r[key_idx]: int(r[val_idx] or 0) for r in c.fetchall()}


def _thous(v):
    """so'm -> ming so'm (frontend ming so'mda ishlaydi)."""
    return round((v or 0) / 1000, 1)


@app.get("/api/dashboard")
def dashboard(days: int = Query(7, ge=1, le=90),
              x_telegram_init_data: str = Header(default="")):
    require_admin(x_telegram_init_data)

    now = get_now()
    today = now.strftime("%Y-%m-%d")
    hourly = days == 1

    if hourly:
        labels_raw = [f"{h:02d}" for h in range(8, 24)]
        date_from = date_to = today
    else:
        dates = [(now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d") for i in range(days)]
        labels_raw = dates
        date_from, date_to = dates[0], dates[-1]

    prev_from = (now - timedelta(days=2 * days - 1)).strftime("%Y-%m-%d")
    prev_to = (now - timedelta(days=days)).strftime("%Y-%m-%d")

    conn = get_conn()
    c = conn.cursor()

    # ── Har kun/soat bo'yicha seriyalar ──
    if hourly:
        bucket = "substr(created_at, 12, 2)"
        rng = ("WHERE date = %s", [today])
        barber = _sum_by(c, f"SELECT {bucket}, SUM(price) FROM services {rng[0]} GROUP BY 1", rng[1])
        fz = _sum_by(c, f"SELECT {bucket}, SUM(price) FROM amoria_bookings WHERE substr(created_at,1,10) = %s GROUP BY 1", [today])
        disco = _sum_by(c, f"SELECT {bucket}, SUM(amount) FROM amoria_disco WHERE substr(created_at,1,10) = %s GROUP BY 1", [today])
        dress = _sum_by(c, f"SELECT {bucket}, SUM(price) FROM dress_sales WHERE business='amoria_dress' AND substr(created_at,1,10) = %s GROUP BY 1", [today])
        imperium = _sum_by(c, f"SELECT {bucket}, SUM(price) FROM dress_sales WHERE business='imperium' AND substr(created_at,1,10) = %s GROUP BY 1", [today])
    else:
        barber = _sum_by(c, "SELECT date, SUM(price) FROM services WHERE date BETWEEN %s AND %s GROUP BY date", [date_from, date_to])
        fz = _sum_by(c, "SELECT substr(created_at,1,10), SUM(price) FROM amoria_bookings WHERE substr(created_at,1,10) BETWEEN %s AND %s GROUP BY 1", [date_from, date_to])
        disco = _sum_by(c, "SELECT date, SUM(amount) FROM amoria_disco WHERE date BETWEEN %s AND %s GROUP BY date", [date_from, date_to])
        dress = _sum_by(c, "SELECT date, SUM(price) FROM dress_sales WHERE business='amoria_dress' AND date BETWEEN %s AND %s GROUP BY date", [date_from, date_to])
        imperium = _sum_by(c, "SELECT date, SUM(price) FROM dress_sales WHERE business='imperium' AND date BETWEEN %s AND %s GROUP BY date", [date_from, date_to])

    series = {
        "barber":   [_thous(barber.get(k, 0)) for k in labels_raw],
        "bar":      [_thous((fz.get(k, 0) or 0) + (disco.get(k, 0) or 0)) for k in labels_raw],
        "dress":    [_thous(dress.get(k, 0)) for k in labels_raw],
        "imperium": [_thous(imperium.get(k, 0)) for k in labels_raw],
    }

    if hourly:
        labels = labels_raw
        label = "Bugun"
    else:
        labels = []
        for d in labels_raw:
            y, m, dd = d.split("-")
            if days <= 7:
                import datetime as _dt
                wd = _dt.date(int(y), int(m), int(dd)).weekday()
                labels.append(WEEKDAYS_UZ[wd])
            else:
                labels.append(str(int(dd)))
        label = f"{days} kun"

    # ── Oldingi davr (delta uchun) ──
    def _total(query, params):
        c.execute(query, params)
        r = c.fetchone()
        return int(r[0] or 0)

    prev_total = (
        _total("SELECT COALESCE(SUM(price),0) FROM services WHERE date BETWEEN %s AND %s", [prev_from, prev_to]) +
        _total("SELECT COALESCE(SUM(price),0) FROM amoria_bookings WHERE substr(created_at,1,10) BETWEEN %s AND %s", [prev_from, prev_to]) +
        _total("SELECT COALESCE(SUM(amount),0) FROM amoria_disco WHERE date BETWEEN %s AND %s", [prev_from, prev_to]) +
        _total("SELECT COALESCE(SUM(price),0) FROM dress_sales WHERE date BETWEEN %s AND %s", [prev_from, prev_to])
    )

    # ── Amallar soni ──
    ops_count = (
        _total("SELECT COUNT(*) FROM services WHERE date BETWEEN %s AND %s", [date_from, date_to]) +
        _total("SELECT COUNT(*) FROM amoria_bookings WHERE substr(created_at,1,10) BETWEEN %s AND %s", [date_from, date_to]) +
        _total("SELECT COUNT(*) FROM amoria_disco WHERE date BETWEEN %s AND %s", [date_from, date_to]) +
        _total("SELECT COUNT(*) FROM dress_sales WHERE date BETWEEN %s AND %s", [date_from, date_to])
    )

    # ── Amoria bo'linishi ──
    amoria_split = {
        "foto": _thous(_total("SELECT COALESCE(SUM(price),0) FROM amoria_bookings WHERE substr(created_at,1,10) BETWEEN %s AND %s", [date_from, date_to])),
        "disco": _thous(_total("SELECT COALESCE(SUM(amount),0) FROM amoria_disco WHERE date BETWEEN %s AND %s", [date_from, date_to])),
    }

    # ── Masterlar (barbershop) ──
    c.execute(
        "SELECT w.id, w.name, wd.start_time, wd.end_time "
        "FROM workers w LEFT JOIN work_days wd ON wd.worker_id = w.id AND wd.date = %s "
        "WHERE w.is_active = 1 AND COALESCE(w.business,'barbershop') = 'barbershop'",
        [today])
    workers_rows = c.fetchall()
    month_from = (now - timedelta(days=29)).strftime("%Y-%m-%d")
    today_sums = _sum_by(c, "SELECT worker_id, SUM(price) FROM services WHERE date = %s GROUP BY worker_id", [today])
    month_sums = _sum_by(c, "SELECT worker_id, SUM(price) FROM services WHERE date BETWEEN %s AND %s GROUP BY worker_id", [month_from, today])

    masters = []
    for wid, name, start_t, end_t in workers_rows:
        if end_t:
            status, since = "done", end_t
        elif start_t:
            status, since = "work", start_t
        else:
            status, since = "off", ""
        masters.append({
            "name": name, "status": status, "since": since or "",
            "today": _thous(today_sums.get(wid, 0)),
            "month": _thous(int((month_sums.get(wid, 0) or 0) * 0.7)),
        })
    masters.sort(key=lambda m: -m["month"])

    # ── Kelgusi bandlar ──
    c.execute("SELECT date, client_name, price, deposit FROM amoria_bookings WHERE date >= %s ORDER BY date LIMIT 6", [today])
    bookings = [{
        "date": f"{r[0][8:10]}.{r[0][5:7]}", "client": r[1],
        "price": _thous(r[2]), "deposit": _thous(r[3]),
    } for r in c.fetchall()]

    # ── So'nggi savdolar (kelin libosi / imperium) ──
    def recent_sales(business):
        c.execute(
            "SELECT ds.date, w.name, ds.price FROM dress_sales ds "
            "LEFT JOIN workers w ON w.id = ds.worker_id "
            "WHERE ds.business = %s ORDER BY ds.id DESC LIMIT 6", [business])
        return [{"date": f"{r[0][8:10]}.{r[0][5:7]}", "worker": r[1] or "—", "price": _thous(r[2])} for r in c.fetchall()]

    dress_sales = recent_sales("amoria_dress")
    imperium_sales = recent_sales("imperium")

    # ── Oxirgi amallar (barcha bizneslar) ──
    c.execute(
        "SELECT * FROM ("
        "  SELECT 'barber' AS biz, s.created_at, s.service_name AS title, w.name AS who, s.price AS amount "
        "    FROM services s LEFT JOIN workers w ON w.id = s.worker_id "
        "  UNION ALL SELECT 'bar', b.created_at, 'Foto zona band', b.client_name, b.price FROM amoria_bookings b "
        "  UNION ALL SELECT 'bar', d2.created_at, 'Disko bar tushumi', NULL, d2.amount FROM amoria_disco d2 "
        "  UNION ALL SELECT CASE WHEN ds.business='amoria_dress' THEN 'dress' ELSE 'imperium' END, "
        "    ds.created_at, CASE WHEN ds.business='amoria_dress' THEN 'Kelin libosi savdosi' ELSE 'Kuyov kostyumi savdosi' END, "
        "    w2.name, ds.price FROM dress_sales ds LEFT JOIN workers w2 ON w2.id = ds.worker_id "
        ") t ORDER BY created_at DESC LIMIT 12")
    BIZ_NAMES = {"barber": "Barbershop", "bar": "Amoria Bar", "dress": "Kelin libosi", "imperium": "Imperium"}
    ops = []
    for biz, created_at, title, who, amount in c.fetchall():
        t = (created_at or "")[11:16]
        d_short = f"{(created_at or '')[8:10]}.{(created_at or '')[5:7]}"
        full_title = f"{title} — {who}" if who else title
        ops.append({
            "biz": biz, "title": full_title,
            "sub": f"{BIZ_NAMES.get(biz, biz)} · {d_short} {t}",
            "amount": _thous(amount),
        })

    conn.close()

    return {
        "label": label,
        "labels": labels,
        "series": series,
        "prev_total": _thous(prev_total),
        "ops_count": ops_count,
        "amoria_split": amoria_split,
        "masters": masters,
        "bookings": bookings,
        "dress_sales": dress_sales,
        "imperium_sales": imperium_sales,
        "ops": ops,
        "owner_name": "Behruz aka",
    }
