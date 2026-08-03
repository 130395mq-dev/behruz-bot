from datetime import datetime, timezone, timedelta
from calendar import monthrange

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import ContextTypes

from database import (
    add_worker, get_all_workers, remove_worker,
    add_dress_sale, get_dress_sale, delete_dress_sale,
    get_dress_sales_range, get_dress_sales_by_worker,
)

TZ = timezone(timedelta(hours=5))

def get_now():
    return datetime.now(TZ)

# Kelin libosi va Imperium uchun umumiy modul.
# Ikkala biznes bir xil ishlaydi: xodim sana + narx kiritadi, admin hisobot ko'radi.
BIZ_CONF = {
    "amoria_dress": {
        "code": "kd",
        "title": "👰 Amoria kelin libosi",
        "item": "kelin libosi",
    },
    "imperium": {
        "code": "im",
        "title": "🏛 Imperium",
        "item": "kuyov kostyumi",
    },
}
CODE2BIZ = {v["code"]: k for k, v in BIZ_CONF.items()}

# Har bir foydalanuvchi holati (barbershop/amoria holatlariga aralashmaydi)
dress_state = {}


def fmt(amount):
    if amount is None:
        amount = 0
    return f"{int(amount):,}".replace(",", " ") + " so'm"


def parse_date(s):
    return datetime.strptime(s.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")


def disp_date(ymd):
    return datetime.strptime(ymd, "%Y-%m-%d").strftime("%d.%m.%Y")


# ─── KLAVIATURALAR ───

def dress_worker_kb():
    kb = [
        [KeyboardButton("➕ Yangi savdo"), KeyboardButton("📋 Savdolarim")],
        [KeyboardButton("📖 Yo'riqnoma")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


def dress_admin_kb():
    kb = [
        [KeyboardButton("📊 Hisobot"), KeyboardButton("👥 Xodimlar")],
        [KeyboardButton("➕ Xodim qo'shish"), KeyboardButton("❌ Xodim o'chirish")],
        [KeyboardButton("💬 Xodimga xabar"), KeyboardButton("📖 Yo'riqnoma")],
        [KeyboardButton("🏢 Biznes almashtirish")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


def dress_report_kb(biz):
    code = BIZ_CONF[biz]["code"]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Bugun", callback_data=f"dr_{code}_1"),
         InlineKeyboardButton("7 kun", callback_data=f"dr_{code}_7")],
        [InlineKeyboardButton("📆 Bu oy", callback_data=f"dr_{code}_month"),
         InlineKeyboardButton("30 kun", callback_data=f"dr_{code}_30")],
        [InlineKeyboardButton("📅 Aniq sana", callback_data=f"dr_{code}_custom")],
    ])


def resolve_period(token):
    today = get_now()
    if token == "month":
        first = today.replace(day=1).strftime("%Y-%m-%d")
        last_day = monthrange(today.year, today.month)[1]
        last = today.replace(day=last_day).strftime("%Y-%m-%d")
        return first, last
    if token.isdigit():
        n = int(token)
        return (today - timedelta(days=n - 1)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    return today.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")


# ─── HISOBOT MATNI ───

def build_dress_report(biz, date_from, date_to):
    conf = BIZ_CONF[biz]
    label = f"{disp_date(date_from)} — {disp_date(date_to)}"
    rows = get_dress_sales_range(biz, date_from, date_to)

    lines = [f"📊 {conf['title']} — hisobot", f"🗓 {label}", ""]
    if not rows:
        lines.append("Savdo yo'q.")
        return "\n".join(lines)

    total = 0
    for r in rows:
        total += r["price"] or 0
        who = r.get("worker_name") or "-"
        lines.append(f"📅 {disp_date(r['date'])} — {who} — {fmt(r['price'])}")

    lines.append("")
    lines.append("─" * 25)
    lines.append(f"📦 Savdolar: {len(rows)} ta")
    lines.append(f"💰 Jami: {fmt(total)}")
    return "\n".join(lines)


# ─── XODIM (ishchi) ───

async def handle_dress_worker(update: Update, context: ContextTypes.DEFAULT_TYPE, worker):
    uid = update.effective_user.id
    text = update.message.text
    biz = worker.get("business")
    conf = BIZ_CONF[biz]
    st = dress_state.get(uid)

    WBTNS = ["➕ Yangi savdo", "📋 Savdolarim", "📖 Yo'riqnoma"]
    if text in WBTNS:
        dress_state.pop(uid, None)
        st = None

    # ── ko'p qadamli holatlar ──
    if isinstance(st, dict):
        step = st.get("step")

        if step == "sale_date":
            try:
                d = parse_date(text)
            except Exception:
                await update.message.reply_text("❌ Format xato! KK.OO.YYYY kiriting\nMasalan: 05.08.2026")
                return
            dress_state[uid] = {**st, "step": "sale_price", "date": d}
            await update.message.reply_text(f"💰 {conf['item'].capitalize()} narxini kiriting (so'm):")
            return

        if step == "sale_price":
            try:
                price = int(text.replace(" ", "").replace(",", ""))
            except ValueError:
                await update.message.reply_text("❌ Faqat raqam kiriting! Masalan: 2000000")
                return
            date = st["date"]
            add_dress_sale(biz, worker["id"], date, price)
            dress_state.pop(uid, None)
            await update.message.reply_text(
                f"✅ Savdo saqlandi!\n\n"
                f"{conf['title']}\n"
                f"📅 {disp_date(date)}\n"
                f"💰 {fmt(price)}",
                reply_markup=dress_worker_kb()
            )
            return

    # ── tugmalar ──
    if text == "➕ Yangi savdo":
        dress_state[uid] = {"step": "sale_date"}
        await update.message.reply_text(
            "📅 Savdo sanasini kiriting (KK.OO.YYYY):\nMasalan: 05.08.2026"
        )
        return

    if text == "📋 Savdolarim":
        rows = get_dress_sales_by_worker(biz, worker["id"], limit=10)
        if not rows:
            await update.message.reply_text("📭 Savdolar yo'q.", reply_markup=dress_worker_kb())
            return
        lines = ["📋 Oxirgi savdolaringiz:\n"]
        kb = []
        for r in rows:
            lines.append(f"📅 {disp_date(r['date'])} — {fmt(r['price'])}")
            kb.append([InlineKeyboardButton(
                f"❌ {disp_date(r['date'])} — {fmt(r['price'])}",
                callback_data=f"dr_del_{r['id']}"
            )])
        lines.append("\nO'chirish uchun tugmani bosing:")
        await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
        return

    if text == "📖 Yo'riqnoma":
        await update.message.reply_text(
            f"📖 {conf['title']} — yo'riqnoma\n\n"
            f"➕ Yangi savdo — haridor kelganda sana va {conf['item']} narxini kiriting.\n"
            "📋 Savdolarim — oxirgi savdolaringizni ko'rish va kerak bo'lsa o'chirish.\n",
            reply_markup=dress_worker_kb()
        )
        return

    await update.message.reply_text("Quyidagi tugmalardan foydalaning:", reply_markup=dress_worker_kb())


# ─── ADMIN ───

async def handle_dress_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, biz):
    uid = update.effective_user.id
    text = update.message.text
    conf = BIZ_CONF[biz]
    st = dress_state.get(uid)

    BTNS = [
        "📊 Hisobot", "👥 Xodimlar", "➕ Xodim qo'shish",
        "❌ Xodim o'chirish", "💬 Xodimga xabar", "📖 Yo'riqnoma",
    ]
    if text in BTNS:
        dress_state.pop(uid, None)
        st = None

    # ── xodim qo'shish ──
    if st == "dr_add_id":
        try:
            tid = int(text.strip())
            dress_state[uid] = {"step": "dr_add_name", "tid": tid}
            await update.message.reply_text("Xodim ismini kiriting:")
        except ValueError:
            await update.message.reply_text("❌ Faqat Telegram ID (raqam) kiriting!")
        return

    if isinstance(st, dict) and st.get("step") == "dr_add_name":
        name = text.strip()
        ok = add_worker(st["tid"], name, business=biz)
        dress_state.pop(uid, None)
        if ok:
            await update.message.reply_text(
                f"✅ {name} qo'shildi! ({conf['title']})\nTelegram ID: {st['tid']}",
                reply_markup=dress_admin_kb()
            )
        else:
            await update.message.reply_text("⚠️ Bu ID allaqachon mavjud.", reply_markup=dress_admin_kb())
        return

    if st == "dr_rm_id":
        try:
            tid = int(text.strip())
            remove_worker(tid)
            dress_state.pop(uid, None)
            await update.message.reply_text("✅ Xodim o'chirildi.", reply_markup=dress_admin_kb())
        except ValueError:
            await update.message.reply_text("❌ Faqat Telegram ID (raqam) kiriting!")
        return

    if isinstance(st, dict) and st.get("step") == "dr_msg_text":
        tid = st["tid"]
        try:
            await context.bot.send_message(chat_id=tid, text=f"💬 Admin xabari:\n\n{text}")
            dress_state.pop(uid, None)
            await update.message.reply_text("✅ Xabar yuborildi!", reply_markup=dress_admin_kb())
        except Exception:
            await update.message.reply_text("❌ Xabar yuborib bo'lmadi.")
        return

    # ── aniq sana hisobot ──
    if isinstance(st, dict) and st.get("step") == "dr_rep_from":
        try:
            df = parse_date(text)
        except Exception:
            await update.message.reply_text("❌ Format xato! KK.OO.YYYY kiriting")
            return
        dress_state[uid] = {**st, "step": "dr_rep_to", "date_from": df}
        await update.message.reply_text("Tugash sanasini kiriting (KK.OO.YYYY):")
        return

    if isinstance(st, dict) and st.get("step") == "dr_rep_to":
        try:
            dt = parse_date(text)
        except Exception:
            await update.message.reply_text("❌ Format xato! KK.OO.YYYY kiriting")
            return
        df = st["date_from"]
        if dt < df:
            await update.message.reply_text("❌ Tugash sanasi boshlanishidan kichik bo'lmasin!")
            return
        rep_biz = st["biz"]
        dress_state.pop(uid, None)
        await update.message.reply_text(build_dress_report(rep_biz, df, dt), reply_markup=dress_admin_kb())
        return

    # ── tugmalar ──
    if text == "📊 Hisobot":
        await update.message.reply_text(
            f"📊 {conf['title']} — davrni tanlang:", reply_markup=dress_report_kb(biz)
        )
        return

    if text == "👥 Xodimlar":
        ws = get_all_workers(biz)
        if not ws:
            await update.message.reply_text("Xodimlar yo'q.", reply_markup=dress_admin_kb())
            return
        lines = [f"👥 {conf['title']} xodimlari:\n"]
        for w in ws:
            lines.append(f"👤 {w['name']} — ID: {w['telegram_id']}")
        await update.message.reply_text("\n".join(lines), reply_markup=dress_admin_kb())
        return

    if text == "➕ Xodim qo'shish":
        dress_state[uid] = "dr_add_id"
        await update.message.reply_text("Yangi xodim Telegram ID sini kiriting:")
        return

    if text == "❌ Xodim o'chirish":
        dress_state[uid] = "dr_rm_id"
        await update.message.reply_text("O'chiriladigan xodim Telegram ID sini kiriting:")
        return

    if text == "💬 Xodimga xabar":
        ws = get_all_workers(biz)
        if not ws:
            await update.message.reply_text("Xodimlar yo'q.", reply_markup=dress_admin_kb())
            return
        kb = [[InlineKeyboardButton(f"👤 {w['name']}", callback_data=f"dr_msgto_{w['telegram_id']}")] for w in ws]
        await update.message.reply_text("Kimga xabar yubormoqchisiz?", reply_markup=InlineKeyboardMarkup(kb))
        return

    if text == "📖 Yo'riqnoma":
        await update.message.reply_text(
            f"📖 {conf['title']} (admin)\n\n"
            f"📊 Hisobot — savdolar ro'yxati va jami summa (davr tanlab).\n"
            f"👥 Xodimlar — {conf['title']} xodimlari ro'yxati.\n"
            "➕/❌ Xodim — xodimni ID orqali qo'shish/o'chirish.\n"
            "💬 Xodimga xabar — botdan xabar yuborish.\n"
            "🏢 Biznes almashtirish — boshqa biznesga o'tish.",
            reply_markup=dress_admin_kb()
        )
        return

    await update.message.reply_text("Quyidagi tugmalardan foydalaning:", reply_markup=dress_admin_kb())


# ─── CALLBACK (dr_ prefiksli) ───

async def handle_dress_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    if data.startswith("dr_del_"):
        sid = int(data.split("_")[2])
        s = get_dress_sale(sid)
        delete_dress_sale(sid)
        if s:
            await q.edit_message_text(f"✅ O'chirildi: {disp_date(s['date'])} — {fmt(s['price'])}")
        else:
            await q.edit_message_text("✅ O'chirildi.")
        return

    if data.startswith("dr_msgto_"):
        tid = int(data.split("_")[2])
        dress_state[uid] = {"step": "dr_msg_text", "tid": tid}
        await q.edit_message_text("💬 Xabar matnini kiriting:")
        return

    parts = data.split("_")  # dr, code, token
    if len(parts) >= 3 and parts[1] in CODE2BIZ:
        biz = CODE2BIZ[parts[1]]
        token = parts[2]
        if token == "custom":
            dress_state[uid] = {"step": "dr_rep_from", "biz": biz}
            await q.edit_message_text("Boshlanish sanasini kiriting (KK.OO.YYYY):\nMasalan: 01.08.2026")
            return
        df, dt = resolve_period(token)
        await q.edit_message_text(build_dress_report(biz, df, dt))
        return
