import os
from datetime import datetime, timezone, timedelta
from calendar import monthrange

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import ContextTypes

from database import (
    add_worker, get_all_workers, remove_worker, worker_exists_message,
    add_amoria_booking, get_amoria_booking, delete_amoria_booking,
    get_amoria_bookings_range, get_amoria_bookings_upcoming,
    add_amoria_disco, get_amoria_disco_range,
)

TZ = timezone(timedelta(hours=5))

def get_now():
    return datetime.now(TZ)

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ADMIN_ID_2 = int(os.getenv("ADMIN_ID_2", "0"))
ADMIN_IDS = [x for x in [ADMIN_ID, ADMIN_ID_2] if x]

# Amoria Bar uchun alohida holat (barbershop holatlariga aralashmaydi)
amoria_state = {}


def fmt(amount):
    if amount is None:
        amount = 0
    return f"{int(amount):,}".replace(",", " ") + " so'm"


def parse_date(s):
    return datetime.strptime(s.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")


def disp_date(ymd):
    return datetime.strptime(ymd, "%Y-%m-%d").strftime("%d.%m.%Y")


# ─── KLAVIATURALAR ───

def amoria_worker_kb():
    kb = [
        [KeyboardButton("📸 Yangi band"), KeyboardButton("📋 Bandlar")],
        [KeyboardButton("🍸 Disko tushum")],
        [KeyboardButton("📖 Yo'riqnoma")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


def amoria_admin_kb():
    kb = [
        [KeyboardButton("📸 Foto zona hisobi"), KeyboardButton("🍸 Disko bar hisobi")],
        [KeyboardButton("📊 Umumiy hisobot")],
        [KeyboardButton("📋 Bandlar ro'yxati"), KeyboardButton("👥 Xodimlar")],
        [KeyboardButton("➕ Xodim qo'shish"), KeyboardButton("❌ Xodim o'chirish")],
        [KeyboardButton("💬 Xodimga xabar"), KeyboardButton("📖 Yo'riqnoma")],
        [KeyboardButton("🏢 Biznes almashtirish")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


def amoria_fz_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📆 Bu oy", callback_data="am_fz_month"),
         InlineKeyboardButton("🔜 Kelgusi 30 kun", callback_data="am_fz_next30")],
        [InlineKeyboardButton("🗂 Hammasi", callback_data="am_fz_all"),
         InlineKeyboardButton("📅 Aniq sana", callback_data="am_fz_custom")],
    ])


def amoria_dc_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Bugun", callback_data="am_dc_1"),
         InlineKeyboardButton("7 kun", callback_data="am_dc_7")],
        [InlineKeyboardButton("30 kun", callback_data="am_dc_30"),
         InlineKeyboardButton("📅 Aniq sana", callback_data="am_dc_custom")],
    ])


def amoria_tot_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📆 Bu oy", callback_data="am_tot_month"),
         InlineKeyboardButton("30 kun", callback_data="am_tot_30")],
        [InlineKeyboardButton("📅 Aniq sana", callback_data="am_tot_custom")],
    ])


def resolve_period(token):
    today = get_now()
    if token == "month":
        first = today.replace(day=1).strftime("%Y-%m-%d")
        last_day = monthrange(today.year, today.month)[1]
        last = today.replace(day=last_day).strftime("%Y-%m-%d")
        return first, last
    if token == "next30":
        return today.strftime("%Y-%m-%d"), (today + timedelta(days=30)).strftime("%Y-%m-%d")
    if token == "all":
        return "2000-01-01", "2999-12-31"
    if token.isdigit():
        n = int(token)
        return (today - timedelta(days=n - 1)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    return today.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")


# ─── HISOBOT MATNI ───

def build_amoria_report(kind, date_from, date_to):
    label = f"{disp_date(date_from)} — {disp_date(date_to)}"

    fz_total = 0
    fz_deposit = 0
    bookings = []
    if kind in ("fz", "tot"):
        bookings = get_amoria_bookings_range(date_from, date_to)
        fz_total = sum((b["price"] or 0) for b in bookings)
        fz_deposit = sum((b["deposit"] or 0) for b in bookings)

    dc_total = 0
    disco = []
    if kind in ("dc", "tot"):
        disco = get_amoria_disco_range(date_from, date_to)
        dc_total = sum((d["total"] or 0) for d in disco)

    if kind == "fz":
        lines = [f"📸 Foto zona hisobi", f"🗓 {label}", ""]
        if not bookings:
            lines.append("Band yo'q.")
        else:
            for b in bookings:
                rem = (b["price"] or 0) - (b["deposit"] or 0)
                lines.append(f"📅 {disp_date(b['date'])} — {b['client_name']} ({b['phone'] or '-'})")
                lines.append(f"   💰 {fmt(b['price'])} | 🔖 {fmt(b['deposit'])} | 🧾 {fmt(rem)}")
            lines.append("")
            lines.append("─" * 25)
            lines.append(f"📦 Bandlar: {len(bookings)} ta")
            lines.append(f"💰 Jami narx: {fmt(fz_total)}")
            lines.append(f"🔖 Jami zalog: {fmt(fz_deposit)}")
            lines.append(f"🧾 Jami qoldiq: {fmt(fz_total - fz_deposit)}")
        return "\n".join(lines)

    if kind == "dc":
        lines = [f"🍸 Disko bar hisobi", f"🗓 {label}", ""]
        if not disco:
            lines.append("Tushum yo'q.")
        else:
            for d in disco:
                lines.append(f"📅 {disp_date(d['date'])} — {fmt(d['total'])}")
            lines.append("")
            lines.append("─" * 25)
            lines.append(f"💰 Jami tushum: {fmt(dc_total)}")
        return "\n".join(lines)

    # tot — umumiy
    lines = [f"📊 Amoria Bar — Umumiy", f"🗓 {label}", ""]
    lines.append("📸 Foto zona:")
    lines.append(f"   💰 Jami narx: {fmt(fz_total)}")
    lines.append(f"   🔖 Zalog olingan: {fmt(fz_deposit)}")
    lines.append(f"   🧾 Qoldiq: {fmt(fz_total - fz_deposit)}")
    lines.append("")
    lines.append("🍸 Disko bar:")
    lines.append(f"   💰 Tushum: {fmt(dc_total)}")
    lines.append("")
    lines.append("─" * 25)
    lines.append(f"💰 Umumiy aylanma (narx + tushum): {fmt(fz_total + dc_total)}")
    return "\n".join(lines)


# ─── XODIM (ishchi) ───

async def handle_amoria_worker(update: Update, context: ContextTypes.DEFAULT_TYPE, worker):
    uid = update.effective_user.id
    text = update.message.text
    st = amoria_state.get(uid)

    # ── ko'p qadamli holatlar ──
    if isinstance(st, dict):
        step = st.get("step")

        if step == "bk_name":
            amoria_state[uid] = {**st, "step": "bk_phone", "client_name": text.strip()}
            await update.message.reply_text("📞 Mijoz telefon raqamini kiriting:")
            return

        if step == "bk_phone":
            amoria_state[uid] = {**st, "step": "bk_date", "phone": text.strip()}
            await update.message.reply_text("📅 Foto sessiya sanasini kiriting (KK.OO.YYYY):\nMasalan: 25.07.2026")
            return

        if step == "bk_date":
            try:
                d = parse_date(text)
            except Exception:
                await update.message.reply_text("❌ Format xato! KK.OO.YYYY kiriting\nMasalan: 25.07.2026")
                return
            amoria_state[uid] = {**st, "step": "bk_price", "date": d}
            await update.message.reply_text("💰 Narxni kiriting (so'm):")
            return

        if step == "bk_price":
            try:
                price = int(text.replace(" ", "").replace(",", ""))
            except ValueError:
                await update.message.reply_text("❌ Faqat raqam kiriting! Masalan: 1500000")
                return
            amoria_state[uid] = {**st, "step": "bk_deposit", "price": price}
            await update.message.reply_text("🔖 Zalog (oldindan to'lov) summasini kiriting (so'm):\nZalog bo'lmasa 0 yozing")
            return

        if step == "bk_deposit":
            try:
                deposit = int(text.replace(" ", "").replace(",", ""))
            except ValueError:
                await update.message.reply_text("❌ Faqat raqam kiriting! Masalan: 500000")
                return
            price = st["price"]
            remaining = price - deposit
            add_amoria_booking(worker["id"], st["client_name"], st["phone"], st["date"], price, deposit)
            amoria_state.pop(uid, None)
            await update.message.reply_text(
                "✅ Band saqlandi!\n\n"
                f"👤 {st['client_name']}\n"
                f"📞 {st['phone']}\n"
                f"📅 {disp_date(st['date'])}\n"
                f"💰 Narx: {fmt(price)}\n"
                f"🔖 Zalog: {fmt(deposit)}\n"
                f"🧾 Qoldiq: {fmt(remaining)}",
                reply_markup=amoria_worker_kb()
            )
            return

        if step == "disco_amount":
            try:
                amount = int(text.replace(" ", "").replace(",", ""))
            except ValueError:
                await update.message.reply_text("❌ Faqat raqam kiriting! Masalan: 3000000")
                return
            date = st["date"]
            add_amoria_disco(worker["id"], date, amount)
            amoria_state.pop(uid, None)
            await update.message.reply_text(
                f"✅ Disko tushum saqlandi!\n📅 {disp_date(date)}\n💰 {fmt(amount)}",
                reply_markup=amoria_worker_kb()
            )
            return

    # ── tugmalar ──
    if text == "📸 Yangi band":
        amoria_state[uid] = {"step": "bk_name"}
        await update.message.reply_text("👤 Mijoz (kelin-kuyov) ismini kiriting:")
        return

    if text == "📋 Bandlar":
        today = get_now().strftime("%Y-%m-%d")
        rows = get_amoria_bookings_upcoming(today)
        if not rows:
            await update.message.reply_text("📭 Kelgusi bandlar yo'q.", reply_markup=amoria_worker_kb())
            return
        lines = ["📋 Kelgusi bandlar:\n"]
        kb = []
        for b in rows:
            rem = (b["price"] or 0) - (b["deposit"] or 0)
            lines.append(f"📅 {disp_date(b['date'])} — {b['client_name']} ({b['phone'] or '-'})")
            lines.append(f"   💰 {fmt(b['price'])} | 🔖 {fmt(b['deposit'])} | 🧾 {fmt(rem)}")
            kb.append([InlineKeyboardButton(f"❌ {disp_date(b['date'])} — {b['client_name']}", callback_data=f"am_bkdel_{b['id']}")])
        await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
        return

    if text == "🍸 Disko tushum":
        today = get_now().strftime("%Y-%m-%d")
        amoria_state[uid] = {"step": "disco_amount", "date": today}
        await update.message.reply_text(
            f"🍸 Disko bar — {disp_date(today)}\nBugungi tushum summasini kiriting (so'm):"
        )
        return

    if text == "📖 Yo'riqnoma":
        await update.message.reply_text(
            "📖 Amoria Bar — yo'riqnoma\n\n"
            "📸 Yangi band — Foto zona uchun: mijoz ismi → telefon → sana → narx → zalog kiriting.\n"
            "📋 Bandlar — Kelgusi bandlarni ko'rish va kerak bo'lsa o'chirish.\n"
            "🍸 Disko tushum — Bugungi disko bar tushumini kiriting.\n",
            reply_markup=amoria_worker_kb()
        )
        return

    await update.message.reply_text("Quyidagi tugmalardan foydalaning:", reply_markup=amoria_worker_kb())


# ─── ADMIN ───

async def handle_amoria_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    st = amoria_state.get(uid)

    BTNS = [
        "📸 Foto zona hisobi", "🍸 Disko bar hisobi", "📊 Umumiy hisobot",
        "📋 Bandlar ro'yxati", "👥 Xodimlar", "➕ Xodim qo'shish",
        "❌ Xodim o'chirish", "💬 Xodimga xabar", "📖 Yo'riqnoma",
    ]
    if text in BTNS:
        amoria_state.pop(uid, None)
        st = None

    # ── xodim qo'shish ──
    if st == "am_add_id":
        try:
            tid = int(text.strip())
            amoria_state[uid] = {"step": "am_add_name", "tid": tid}
            await update.message.reply_text("Xodim ismini kiriting:")
        except ValueError:
            await update.message.reply_text("❌ Faqat Telegram ID (raqam) kiriting!")
        return

    if isinstance(st, dict) and st.get("step") == "am_add_name":
        name = text.strip()
        ok = add_worker(st["tid"], name, business="amoria_bar")
        amoria_state.pop(uid, None)
        if ok:
            await update.message.reply_text(
                f"✅ {name} qo'shildi! (Amoria Bar)\nTelegram ID: {st['tid']}",
                reply_markup=amoria_admin_kb()
            )
        else:
            await update.message.reply_text(worker_exists_message(st["tid"]), reply_markup=amoria_admin_kb())
        return

    if st == "am_rm_id":
        try:
            tid = int(text.strip())
            remove_worker(tid)
            amoria_state.pop(uid, None)
            await update.message.reply_text("✅ Xodim o'chirildi.", reply_markup=amoria_admin_kb())
        except ValueError:
            await update.message.reply_text("❌ Faqat Telegram ID (raqam) kiriting!")
        return

    if isinstance(st, dict) and st.get("step") == "am_msg_text":
        tid = st["tid"]
        try:
            await context.bot.send_message(chat_id=tid, text=f"💬 Admin xabari:\n\n{text}")
            amoria_state.pop(uid, None)
            await update.message.reply_text("✅ Xabar yuborildi!", reply_markup=amoria_admin_kb())
        except Exception:
            await update.message.reply_text("❌ Xabar yuborib bo'lmadi.")
        return

    # ── aniq sana hisobot ──
    if isinstance(st, dict) and st.get("step") == "am_rep_from":
        try:
            df = parse_date(text)
        except Exception:
            await update.message.reply_text("❌ Format xato! KK.OO.YYYY kiriting")
            return
        amoria_state[uid] = {**st, "step": "am_rep_to", "date_from": df}
        await update.message.reply_text("Tugash sanasini kiriting (KK.OO.YYYY):")
        return

    if isinstance(st, dict) and st.get("step") == "am_rep_to":
        try:
            dt = parse_date(text)
        except Exception:
            await update.message.reply_text("❌ Format xato! KK.OO.YYYY kiriting")
            return
        df = st["date_from"]
        if dt < df:
            await update.message.reply_text("❌ Tugash sanasi boshlanishidan kichik bo'lmasin!")
            return
        kind = st["kind"]
        amoria_state.pop(uid, None)
        await update.message.reply_text(build_amoria_report(kind, df, dt), reply_markup=amoria_admin_kb())
        return

    # ── tugmalar ──
    if text == "📸 Foto zona hisobi":
        await update.message.reply_text("📸 Foto zona — davrni tanlang:", reply_markup=amoria_fz_kb())
        return

    if text == "🍸 Disko bar hisobi":
        await update.message.reply_text("🍸 Disko bar — davrni tanlang:", reply_markup=amoria_dc_kb())
        return

    if text == "📊 Umumiy hisobot":
        await update.message.reply_text("📊 Umumiy — davrni tanlang:", reply_markup=amoria_tot_kb())
        return

    if text == "📋 Bandlar ro'yxati":
        today = get_now().strftime("%Y-%m-%d")
        rows = get_amoria_bookings_upcoming(today)
        if not rows:
            await update.message.reply_text("📭 Kelgusi bandlar yo'q.", reply_markup=amoria_admin_kb())
            return
        lines = ["📋 Kelgusi bandlar:\n"]
        for b in rows:
            rem = (b["price"] or 0) - (b["deposit"] or 0)
            lines.append(f"📅 {disp_date(b['date'])} — {b['client_name']} ({b['phone'] or '-'})")
            lines.append(f"   💰 {fmt(b['price'])} | 🔖 {fmt(b['deposit'])} | 🧾 {fmt(rem)}")
        await update.message.reply_text("\n".join(lines), reply_markup=amoria_admin_kb())
        return

    if text == "👥 Xodimlar":
        ws = get_all_workers("amoria_bar")
        if not ws:
            await update.message.reply_text("Xodimlar yo'q.", reply_markup=amoria_admin_kb())
            return
        lines = ["👥 Amoria Bar xodimlari:\n"]
        for w in ws:
            lines.append(f"👤 {w['name']} — ID: {w['telegram_id']}")
        await update.message.reply_text("\n".join(lines), reply_markup=amoria_admin_kb())
        return

    if text == "➕ Xodim qo'shish":
        amoria_state[uid] = "am_add_id"
        await update.message.reply_text("Yangi xodim Telegram ID sini kiriting:")
        return

    if text == "❌ Xodim o'chirish":
        amoria_state[uid] = "am_rm_id"
        await update.message.reply_text("O'chiriladigan xodim Telegram ID sini kiriting:")
        return

    if text == "💬 Xodimga xabar":
        ws = get_all_workers("amoria_bar")
        if not ws:
            await update.message.reply_text("Xodimlar yo'q.", reply_markup=amoria_admin_kb())
            return
        kb = [[InlineKeyboardButton(f"👤 {w['name']}", callback_data=f"am_msgto_{w['telegram_id']}")] for w in ws]
        await update.message.reply_text("Kimga xabar yubormoqchisiz?", reply_markup=InlineKeyboardMarkup(kb))
        return

    if text == "📖 Yo'riqnoma":
        await update.message.reply_text(
            "📖 Amoria Bar (admin)\n\n"
            "📸 Foto zona hisobi — band qilingan sessiyalar: narx, zalog, qoldiq.\n"
            "🍸 Disko bar hisobi — kunlik tushumlar.\n"
            "📊 Umumiy hisobot — foto zona + disko bar birga.\n"
            "📋 Bandlar ro'yxati — kelgusi bandlar.\n"
            "➕/❌ Xodim — Amoria Bar xodimini qo'shish/o'chirish.\n"
            "💬 Xodimga xabar — botdan xabar yuborish.\n"
            "🏢 Biznes almashtirish — boshqa biznesga o'tish.",
            reply_markup=amoria_admin_kb()
        )
        return

    await update.message.reply_text("Quyidagi tugmalardan foydalaning:", reply_markup=amoria_admin_kb())


# ─── CALLBACK (am_ prefiksli) ───

async def handle_amoria_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    if data.startswith("am_bkdel_"):
        bid = int(data.split("_")[2])
        b = get_amoria_booking(bid)
        delete_amoria_booking(bid)
        if b:
            await q.edit_message_text(f"✅ O'chirildi: {disp_date(b['date'])} — {b['client_name']}")
        else:
            await q.edit_message_text("✅ O'chirildi.")
        return

    if data.startswith("am_msgto_"):
        tid = int(data.split("_")[2])
        amoria_state[uid] = {"step": "am_msg_text", "tid": tid}
        await q.edit_message_text("💬 Xabar matnini kiriting:")
        return

    parts = data.split("_")  # am, kind, token
    if len(parts) >= 3 and parts[1] in ("fz", "dc", "tot"):
        kind = parts[1]
        token = parts[2]
        if token == "custom":
            amoria_state[uid] = {"step": "am_rep_from", "kind": kind}
            await q.edit_message_text("Boshlanish sanasini kiriting (KK.OO.YYYY):\nMasalan: 01.07.2026")
            return
        df, dt = resolve_period(token)
        await q.edit_message_text(build_amoria_report(kind, df, dt))
        return
