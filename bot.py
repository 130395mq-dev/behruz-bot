import os
import asyncio
from datetime import datetime, timezone, timedelta, time as dtime
from dotenv import load_dotenv

TZ = timezone(timedelta(hours=5))

def get_now():
    return datetime.now(TZ)
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)
from database import (
    init_db, get_worker, get_all_workers, add_worker, remove_worker,
    start_work_day, end_work_day, get_work_day, get_all_sessions,
    allow_restart, get_next_session,
    add_service, delete_last_service, get_services_by_worker_date,
    get_services_by_worker_range, get_worker_summary_range,
    get_all_workers_summary_range, get_today_summary_all,
    workers_not_started, workers_not_ended, set_holiday,
    add_appointment, get_appointments, get_all_appointments, delete_appointment,
    SERVICE_NAMES
)

from amoria import (
    amoria_worker_kb, amoria_admin_kb,
    handle_amoria_worker, handle_amoria_admin, handle_amoria_callback,
)

from dress import (
    BIZ_CONF, dress_worker_kb, dress_admin_kb,
    handle_dress_worker, handle_dress_admin, handle_dress_callback,
    dress_state,
)
from amoria import amoria_state

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
ADMIN_ID_2 = int(os.getenv("ADMIN_ID_2", "0"))
ADMIN_IDS = [ADMIN_ID] + ([ADMIN_ID_2] if ADMIN_ID_2 else [])

STICKER_LAUGH = "CAACAgIAAxkBAAIBv2RtQkLbMnY1oqRzvXBHJJGpuHmVAAIUAANWnb0KODBFMQbMrUsvBA"

ENTER_PRICE, ENTER_WORKER_ID, ENTER_WORKER_NAME, ENTER_REMOVE_ID, ENTER_HOLIDAY = range(5)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ─── BIZNES TANLASH ───
# Admin botga kirganda qaysi biznes bilan ishlashini tanlaydi.
BUSINESS_BTN = {
    "💈 Barbershop": "barbershop",
    "🍸 Amoria Bar": "amoria_bar",
    "👰 Amoria kelin libosi": "amoria_dress",
    "🏛 Imperium": "imperium",
}

# Admin -> hozir tanlangan biznes
current_business = {}

def get_business_keyboard():
    kb = [
        [KeyboardButton("💈 Barbershop"), KeyboardButton("🍸 Amoria Bar")],
        [KeyboardButton("👰 Amoria kelin libosi"), KeyboardButton("🏛 Imperium")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def get_admin_kb_for(biz):
    if biz == "amoria_bar":
        return amoria_admin_kb()
    if biz in BIZ_CONF:
        return dress_admin_kb()
    return get_admin_keyboard()

def format_money(amount) -> str:
    if amount is None:
        amount = 0
    return f"{int(amount):,}".replace(",", " ") + " so'm"

def calc_percent(total):
    worker = int(total * 0.7)
    owner = int(total * 0.3)
    return worker, owner

async def reply_clean(update, text, reply_markup=None):
    try:
        await update.message.delete()
    except:
        pass
    return await update.message.reply_text(text, reply_markup=reply_markup)

def get_worker_keyboard():
    kb = [
        [KeyboardButton("🌅 Kunni boshlash"), KeyboardButton("✅ Kunni yakunlash")],
        [KeyboardButton("✂️ Xizmatlar"), KeyboardButton("📊 Hisobot")],
        [KeyboardButton("📅 Mijoz qabul"), KeyboardButton("📖 Yo'riqnoma")],
        [KeyboardButton("👑 Admin panel")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def get_services_keyboard():
    kb = [
        [KeyboardButton("✂️ Soch olish"), KeyboardButton("🚿 Soch yuvish")],
        [KeyboardButton("🪒 Soqol olish"), KeyboardButton("👰 Kiyov tayyorlash")],
        [KeyboardButton("💆 Yuz tozalash"), KeyboardButton("🎭 Maska")],
        [KeyboardButton("🎨 Soch bo'yash"), KeyboardButton("🔧 Boshqa xizmat")],
        [KeyboardButton("🗑 Oxirgini o'chir"), KeyboardButton("🔙 Orqaga")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def get_report_keyboard():
    kb = [
        [KeyboardButton("📊 Bugungi hisobot"), KeyboardButton("📈 Shaxsiy rekord")],
        [KeyboardButton("📅 Aniq sana hisoboti"), KeyboardButton("🔙 Orqaga")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def get_admin_keyboard():
    kb = [
        [KeyboardButton("👥 Masterlar"), KeyboardButton("📊 Umumiy hisobot")],
        [KeyboardButton("📅 Qabullar"), KeyboardButton("🏆 Eng yaxshi master")],
        [KeyboardButton("💸 Oylik maosh"), KeyboardButton("💬 Xodimga xabar")],
        [KeyboardButton("📢 Hammaga xabar"), KeyboardButton("📅 Dam olish kuni belgilash")],
        [KeyboardButton("🗓 Dam olishni bekor qilish"), KeyboardButton("➕ Xodim qo'shish")],
        [KeyboardButton("❌ Xodim o'chirish"), KeyboardButton("📖 Yo'riqnoma")],
        [KeyboardButton("🏢 Biznes almashtirish")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def get_report_period_keyboard(prefix="report"):
    kb = [
        [InlineKeyboardButton("1 kunlik", callback_data=f"{prefix}_1"),
         InlineKeyboardButton("3 kunlik", callback_data=f"{prefix}_3")],
        [InlineKeyboardButton("7 kunlik", callback_data=f"{prefix}_7"),
         InlineKeyboardButton("15 kunlik", callback_data=f"{prefix}_15")],
        [InlineKeyboardButton("1 oylik", callback_data=f"{prefix}_30"),
         InlineKeyboardButton("📅 Aniq sana", callback_data=f"{prefix}_custom")],
    ]
    return InlineKeyboardMarkup(kb)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if is_admin(user_id):
        current_business.pop(user_id, None)
        await update.message.reply_text(
            "👑 Xush kelibsiz, Behruz aka!\n🏢 Qaysi biznes bilan ishlaymiz?",
            reply_markup=get_business_keyboard()
        )
        return

    worker = get_worker(user_id)
    if worker:
        biz = worker.get("business") or "barbershop"
        if biz == "amoria_bar":
            await update.message.reply_text(
                f"🍸 Salom, {worker['name']}! Amoria Bar.",
                reply_markup=amoria_worker_kb()
            )
        elif biz in BIZ_CONF:
            await update.message.reply_text(
                f"Salom, {worker['name']}! {BIZ_CONF[biz]['title']}.",
                reply_markup=dress_worker_kb()
            )
        else:
            await update.message.reply_text(
                f"Salom, {worker['name']}! 💈\nBugun ham zo'r ish qiling!",
                reply_markup=get_worker_keyboard()
            )
    else:
        await update.message.reply_text(
            "❌ Siz tizimda ro'yxatdan o'tmagansiz.\nAdmin bilan bog'laning."
        )
        try:
            first = update.effective_user.first_name or ""
            username = f"@{update.effective_user.username}" if update.effective_user.username else "username yo'q"
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🔔 Yangi foydalanuvchi botga kirdi!\n👤 Ismi: {first}\n🔗 {username}\n🆔 ID: {user_id}"
            )
        except:
            pass

# ─── SERVICE HANDLER ───

pending_service = {}

async def handle_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if is_admin(user_id):
        # ── Biznes tanlash ──
        if text in BUSINESS_BTN:
            biz = BUSINESS_BTN[text]
            admin_state.pop(user_id, None)
            amoria_state.pop(user_id, None)
            dress_state.pop(user_id, None)
            if biz == "barbershop":
                current_business[user_id] = biz
                await update.message.reply_text("💈 Barbershop", reply_markup=get_admin_keyboard())
            elif biz == "amoria_bar":
                current_business[user_id] = biz
                await update.message.reply_text("🍸 Amoria Bar", reply_markup=amoria_admin_kb())
            else:
                current_business[user_id] = biz
                await update.message.reply_text(BIZ_CONF[biz]["title"], reply_markup=dress_admin_kb())
            return

        if text == "🏢 Biznes almashtirish":
            current_business.pop(user_id, None)
            admin_state.pop(user_id, None)
            amoria_state.pop(user_id, None)
            dress_state.pop(user_id, None)
            await update.message.reply_text("🏢 Qaysi biznes bilan ishlaymiz?", reply_markup=get_business_keyboard())
            return

        biz = current_business.get(user_id)
        if not biz:
            await update.message.reply_text("🏢 Avval biznesni tanlang:", reply_markup=get_business_keyboard())
            return
        if biz == "barbershop":
            await handle_admin_message(update, context)
        elif biz == "amoria_bar":
            await handle_amoria_admin(update, context)
        elif biz in BIZ_CONF:
            await handle_dress_admin(update, context, biz)
        else:
            current_business.pop(user_id, None)
            await update.message.reply_text("🏢 Avval biznesni tanlang:", reply_markup=get_business_keyboard())
        return

    worker = get_worker(user_id)
    if not worker:
        await update.message.reply_text("❌ Siz tizimda yo'qsiz.")
        return

    # ── Amoria Bar xodimi ──
    worker_biz = worker.get("business") or "barbershop"
    if worker_biz == "amoria_bar":
        await handle_amoria_worker(update, context, worker)
        return

    # ── Kelin libosi / Imperium xodimi ──
    if worker_biz in BIZ_CONF:
        await handle_dress_worker(update, context, worker)
        return

    today = get_now().strftime("%Y-%m-%d")
    work_day = get_work_day(worker["id"], today)

    # ── Kunni boshlash ──
    if text == "🌅 Kunni boshlash":
        from database import get_conn
        today_str = get_now().strftime("%Y-%m-%d")
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT is_holiday FROM work_days WHERE worker_id = %s AND date = %s AND is_holiday = 1",
            (worker["id"], today_str)
        )
        holiday = c.fetchone()
        conn.close()
        if holiday:
            await update.message.reply_text("🎉 Bugun dam olish kuni! Hordiq oling 😊")
            return
        result = start_work_day(worker["id"])
        if result:
            current_time_str = get_now().strftime("%H:%M")
            await update.message.reply_text(
                f"✅ Ish kuni boshlandi!\n🕐 Boshlash vaqti: {current_time_str}",
                reply_markup=get_worker_keyboard()
            )
        else:
            # Check if day was ended - suggest admin restart
            today_check = get_now().strftime("%Y-%m-%d")
            wd_check = get_work_day(worker["id"], today_check)
            if wd_check and wd_check.get("end_time"):
                await update.message.reply_text(
                    "⚠️ Siz bugun kunni yakunlagansiz!\n\n"
                    "Qayta boshlash uchun admindan ruxsat so'rang."
                )
            else:
                await update.message.reply_text("⚠️ Siz bugun allaqachon ish kunini boshlagansiz.")
        return

    # ── Kunni yakunlash ──
    if text == "✅ Kunni yakunlash":
        work_day_check = get_work_day(worker["id"], today)
        if not work_day_check or not work_day_check["start_time"]:
            await update.message.reply_text("⚠️ Avval kunni boshlang!")
            return
        if work_day_check["end_time"]:
            await update.message.reply_text("⚠️ Kun allaqachon yakunlangan.")
            return

        services_check = get_services_by_worker_date(worker["id"], today)
        total_check = sum(s["total"] for s in services_check)
        current_time = get_now().strftime("%H:%M")

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ha, yakunla", callback_data=f"endday_{worker['id']}"),
             InlineKeyboardButton("❌ Yo'q", callback_data="endday_cancel")]
        ])
        await update.message.reply_text(
            f"⚠️ Kunni yakunlamoqchimisiz?\n\n"
            f"🕐 Hozirgi vaqt: {current_time}\n"
            f"💰 Bugungi jami: {format_money(total_check)}",
            reply_markup=kb
        )
        return

    if False:  # placeholder — real end handled in callback
        result = end_work_day(worker["id"])
        if not result:
            await update.message.reply_text("⚠️ Avval kunni boshlang yoki allaqachon yakunlangan.")
            return

        services = get_services_by_worker_date(worker["id"], today)
        total = sum(s["total"] for s in services)
        worker_share, owner_share = calc_percent(total)
        current_time_str = get_now().strftime("%H:%M")

        lines = [f"✅ {worker['name']} ish kunini yakunladi"]
        lines.append(f"🕐 {result['start']} — {result['end']}")

        if result["start"] and result["end"]:
            try:
                fmt = "%H:%M"
                delta = datetime.strptime(result["end"], fmt) - datetime.strptime(result["start"], fmt)
                h, m = divmod(int(delta.total_seconds()) // 60, 60)
                lines.append(f"⏱ Ish vaqti: {h} soat {m} daqiqa")
            except:
                pass

        lines.append("")
        lines.append("📋 Xizmatlar:")
        for s in services:
            lines.append(f"  {s['service_name']} × {s['cnt']} — {format_money(s['total'])}")

        lines.append("")
        lines.append("─" * 25)
        lines.append(f"💰 Jami: {format_money(total)}")
        lines.append(f"👤 {worker['name']} (70%): {format_money(worker_share)}")
        lines.append(f"👑 Egasiga (30%): {format_money(owner_share)}")

        msg = "\n".join(lines)
        await update.message.reply_text(msg, reply_markup=get_worker_keyboard())

        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=aid, text=f"🔔 {msg}")
            except:
                pass
        return

    # ── Hisobotim (eski) ──
    if text == "📊 Hisobotim":
        await update.message.reply_text("Hisobot turini tanlang:", reply_markup=get_report_keyboard())
        return

    # ── Oxirgini o'chir ──
    if text == "🗑 Oxirgini o'chir":
        if work_day and work_day.get("end_time"):
            await update.message.reply_text("⚠️ Siz kunni yakunlagansiz! O'zgartirish mumkin emas.")
            return
        from database import get_conn
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT id, service_name, price, created_at FROM services "
            "WHERE worker_id = %s AND date = %s ORDER BY id",
            (worker["id"], today)
        )
        rows = c.fetchall()
        conn.close()
        if not rows:
            await update.message.reply_text("⚠️ Bugun hali xizmat kiritilmagan.", reply_markup=get_worker_keyboard())
            return
        kb = []
        for row in rows:
            sid, sname, sprice, screated = row
            time_str = screated[11:16] if len(screated) > 11 else ""
            kb.append([InlineKeyboardButton(
                f"{sname} — {format_money(sprice)} ({time_str})",
                callback_data=f"delservice_{sid}_{worker['id']}"
            )])
        kb.append([InlineKeyboardButton("❌ Bekor qilish", callback_data="delservice_cancel")])
        await update.message.reply_text(
            "Qaysi yozuvni o'chirmoqchisiz?",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # ── Admin panel (xodim bosadi) ──
    if text == "👑 Admin panel":
        await update.message.reply_text(
            "👑 Bu bo'lim faqat Behruz aka uchun!\nSiz esa master! 😄🤣"
        )
        return

    # ── Mijoz qabul ──
    if text == "📅 Mijoz qabul":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Bugun", callback_data=f"appt_new_{worker['id']}_today"),
             InlineKeyboardButton("📅 Ertaga", callback_data=f"appt_new_{worker['id']}_tomorrow")],
            [InlineKeyboardButton("📋 Bugungi qabullar", callback_data=f"appt_list_{worker['id']}_today"),
             InlineKeyboardButton("📋 Ertangi qabullar", callback_data=f"appt_list_{worker['id']}_tomorrow")],
        ])
        await update.message.reply_text("📅 Mijoz qabul:", reply_markup=kb)
        return

    # ── Kategoriyalar ──
    if text == "✂️ Xizmatlar":
        await update.message.reply_text("Xizmatni tanlang:", reply_markup=get_services_keyboard())
        return

    if text == "📊 Hisobot":
        await update.message.reply_text("Hisobot turini tanlang:", reply_markup=get_report_keyboard())
        return

    if text == "🔙 Orqaga":
        await update.message.reply_text("Asosiy menyu:", reply_markup=get_worker_keyboard())
        return

    if text == "📊 Bugungi hisobot":
        services = get_services_by_worker_date(worker["id"], today)
        total = sum(s["total"] for s in services)
        worker_share, _ = calc_percent(total)
        work_day = get_work_day(worker["id"], today)
        lines = [f"📊 {worker['name']} — Bugungi hisobot"]
        lines.append(f"📅 {get_now().strftime('%d.%m.%Y')}")
        if work_day and work_day.get("start_time"):
            if work_day.get("end_time"):
                lines.append(f"🕐 {work_day['start_time']} — {work_day['end_time']}")
            else:
                lines.append(f"🕐 Boshlash: {work_day['start_time']}")
        lines.append("")
        if services:
            for s in services:
                lines.append(f"{s['service_name']} × {s['cnt']} — {format_money(s['total'])}")
            lines.append("")
            lines.append("─" * 25)
            lines.append(f"💰 Jami: {format_money(total)}")
            lines.append(f"👤 Sizniki (70%): {format_money(worker_share)}")
        else:
            lines.append("Bugun hali xizmat kiritilmagan.")
        await update.message.reply_text("\n".join(lines), reply_markup=get_report_keyboard())
        return

    if text == "📈 Shaxsiy rekord":
        from database import get_conn
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT date, SUM(price) as total FROM services WHERE worker_id = %s "
            "GROUP BY date ORDER BY total DESC LIMIT 1",
            (worker["id"],)
        )
        row = c.fetchone()
        conn.close()
        if row:
            d = datetime.strptime(row[0], "%Y-%m-%d").strftime("%d.%m.%Y")
            lines = [f"📈 {worker['name']} — Shaxsiy rekord"]
            lines.append(f"📅 {d}")
            lines.append(f"💰 {format_money(row[1])}")
            lines.append(f"👤 Sizniki (70%): {format_money(int(row[1]*0.7))}")
            await update.message.reply_text("\n".join(lines), reply_markup=get_report_keyboard())
        else:
            await update.message.reply_text("Hali ma'lumot yo'q.", reply_markup=get_report_keyboard())
        return

    if text == "📅 Aniq sana hisoboti":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Aniq sana", callback_data=f"myreport_{worker['id']}_custom")],
        ])
        await update.message.reply_text("Qaysi davr?", reply_markup=kb)
        return

    # ── Yo'riqnoma (xodim) ──
    if text == "📖 Yo'riqnoma":
        await update.message.reply_text(
            "📖 Botdan foydalanish yo'riqnomasi\n\n"
            "🌅 Kunni boshlash — Ishni boshlaganingizda bosing\n"
            "✅ Kunni yakunlash — Ishni tugatganingizda bosing\n\n"
            "✂️ Soch olish, 🚿 Soch yuvish va boshqa tugmalar — "
            "Xizmat ko'rsatganda bosing va narxni kiriting\n\n"
            "🔧 Boshqa xizmat — Ro'yxatda yo'q xizmat uchun, "
            "nom va narxni o'zingiz kiriting\n\n"
            "🗑 Oxirgini o'chir — Noto'g'ri kiritgan bo'lsangiz, "
            "ro'yxatdan tanlang va o'chiring\n\n"
            "📊 Hisobotim — Bugun yoki ma'lum davr uchun o'z daromadingizni ko'ring\n"
            "📈 Shaxsiy rekord — Eng ko'p ishlagan kuningizni ko'ring\n\n"
            "👑 Admin panel — Faqat Behruz aka uchun 😄",
            reply_markup=get_worker_keyboard()
        )
        return

    # ── Mijoz qabul state (xodim) ──
    user_state = admin_state.get(user_id)
    if isinstance(user_state, dict) and user_state.get("step") == "waiting_client_name":
        admin_state[user_id] = {**user_state, "step": "waiting_client_time", "client_name": text.strip()}
        await update.message.reply_text("Vaqtni kiriting (HH:MM):\nMasalan: 14:30")
        return

    if isinstance(user_state, dict) and user_state.get("step") == "waiting_client_time":
        try:
            datetime.strptime(text.strip(), "%H:%M")
            time_str = text.strip()
            worker_id = user_state["worker_id"]
            date_str = user_state["date"]
            label = user_state["label"]
            client_name = user_state["client_name"]
            add_appointment(worker_id, date_str, time_str, client_name)
            admin_state.pop(user_id)
            await update.message.reply_text(
                f"✅ Saqlandi!\n📅 {label.capitalize()}\n🕐 {time_str} — {client_name}",
                reply_markup=get_worker_keyboard()
            )
        except ValueError:
            await update.message.reply_text("❌ Format xato! HH:MM kiriting\nMasalan: 14:30")
        return

    # ── Aniq sana (xodim) ──
    if isinstance(user_state, dict) and user_state.get("type") == "worker":
        if user_state.get("step") == "waiting_date_from":
            try:
                today_str = get_now().strftime("%Y-%m-%d")
                tomorrow_str = (get_now() + timedelta(days=1)).strftime("%Y-%m-%d")
                if len(text.strip()) == 7 and text.strip()[2] == ".":
                    month, year = text.strip().split(".")
                    from calendar import monthrange
                    days_in_month = monthrange(int(year), int(month))[1]
                    date_from = f"{year}-{month.zfill(2)}-01"
                    date_to = f"{year}-{month.zfill(2)}-{str(days_in_month).zfill(2)}"
                else:
                    d = datetime.strptime(text.strip(), "%d.%m.%Y")
                    date_from = d.strftime("%Y-%m-%d")
                    date_to = None
                if date_from >= tomorrow_str:
                    await update.message.reply_text("❌ Kelajak sanani kiritib bo'lmaydi!")
                    return
                admin_state[user_id] = {**user_state, "step": "waiting_date_to", "date_from": date_from}
                if date_to:
                    await generate_custom_report(update, context, user_state, date_from, date_to)
                    admin_state.pop(user_id)
                else:
                    await update.message.reply_text("Tugash sanasini kiriting (KK.OO.YYYY):\nMasalan: 18.06.2026")
            except:
                await update.message.reply_text("❌ Format xato! OO.YYYY yoki KK.OO.YYYY kiriting")
            return

        if user_state.get("step") == "waiting_date_to":
            try:
                today_str = get_now().strftime("%Y-%m-%d")
                tomorrow_str = (get_now() + timedelta(days=1)).strftime("%Y-%m-%d")
                try:
                    d = datetime.strptime(text.strip(), "%d.%m.%Y")
                except ValueError:
                    await update.message.reply_text("❌ Format xato! KK.OO.YYYY kiriting\nMasalan: 18.06.2026")
                    return
                date_to = d.strftime("%Y-%m-%d")
                date_from = user_state["date_from"]
                if date_to >= tomorrow_str:
                    await update.message.reply_text("❌ Kelajak sanani kiritib bo'lmaydi!")
                    return
                if date_to < date_from:
                    await update.message.reply_text("❌ Tugash sanasi boshlanish sanasidan kichik bo'lmasin!")
                    return
                await generate_custom_report(update, context, user_state, date_from, date_to)
                admin_state.pop(user_id)
            except Exception as e:
                await update.message.reply_text("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")
            return

    # ── Boshqa xizmat ──
    if text == "🔧 Boshqa xizmat":
        if not work_day or not work_day["start_time"]:
            await update.message.reply_text("⚠️ Avval '🌅 Kunni boshlash' ni bosing!")
            return
        if work_day and work_day.get("end_time"):
            await update.message.reply_text("⚠️ Siz kunni yakunlagansiz!")
            return
        pending_service[user_id] = "🔧 boshqa_nom"
        await update.message.reply_text("Xizmat nomini kiriting:")
        return

    # ── Shaxsiy rekord ──
    if text == "📈 Shaxsiy rekord":
        from database import get_conn, dict_row as _dr
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT date, SUM(price) as total FROM services WHERE worker_id = %s "
            "GROUP BY date ORDER BY total DESC LIMIT 1",
            (worker["id"],)
        )
        row = c.fetchone()
        conn.close()
        if row:
            d = datetime.strptime(row[0], "%Y-%m-%d").strftime("%d.%m.%Y")
            lines = [f"📈 {worker['name']} — Shaxsiy rekord"]
            lines.append(f"📅 {d}")
            lines.append(f"💰 {format_money(row[1])}")
            lines.append(f"👤 Sizniki (70%): {format_money(int(row[1]*0.7))}")
            await update.message.reply_text("\n".join(lines), reply_markup=get_worker_keyboard())
        else:
            await update.message.reply_text("Hali ma'lumot yo'q.", reply_markup=get_worker_keyboard())
        return

    # ── Xizmat tanlash ──
    if text in SERVICE_NAMES:
        if not work_day or not work_day["start_time"]:
            await update.message.reply_text("⚠️ Avval '🌅 Kunni boshlash' ni bosing!")
            return
        if work_day and work_day["end_time"]:
            await update.message.reply_text("⚠️ Siz kunni yakunlagansiz! Yangi kun uchun '🌅 Kunni boshlash' ni bosing.")
            return
        pending_service[user_id] = text
        await update.message.reply_text(f"{text} uchun narxni kiriting (so'm):")
        return

    # ── Narx kiritish ──
    if user_id in pending_service:
        service = pending_service[user_id]
        # Boshqa xizmat - 1-qadam: nom kiritish
        if service == "🔧 boshqa_nom":
            pending_service[user_id] = f"🔧 {text.strip()}"
            await update.message.reply_text(f"Narxni kiriting (so'm):")
            return
        # Narx kiritish
        try:
            price = int(text.replace(" ", "").replace(",", ""))
            service_name = pending_service.pop(user_id)
            add_service(worker["id"], service_name, price)
            await update.message.reply_text(
                f"✅ Saqlandi!\n{service_name} — {format_money(price)}\n📅 {get_now().strftime('%d.%m.%Y %H:%M')}",
                reply_markup=get_worker_keyboard()
            )
        except ValueError:
            await update.message.reply_text("❌ Faqat raqam kiriting! Masalan: 70000")
        return

# ─── ADMIN HANDLERS ───

admin_state = {}

async def generate_custom_report(update, context, state, date_from, date_to):
    from database import get_conn
    conn = get_conn()
    c = conn.cursor()
    label = f"{date_from[8:]}.{date_from[5:7]}.{date_from[:4]} — {date_to[8:]}.{date_to[5:7]}.{date_to[:4]}"

    if state.get("type") == "worker":
        worker_id = state["worker_id"]
        c.execute(
            "SELECT w.name, COALESCE(SUM(s.price),0) as total FROM workers w "
            "LEFT JOIN services s ON w.id = s.worker_id AND s.date BETWEEN %s AND %s "
            "WHERE w.id = %s GROUP BY w.name",
            (date_from, date_to, worker_id)
        )
        row = c.fetchone()
        conn.close()
        if row:
            name, total = row
            w_share, o_share = calc_percent(total)
            lines = [f"👤 {name} — {label}", f"💰 Jami: {format_money(total)}", f"👤 Sizniki (70%): {format_money(w_share)}"]
            await update.message.reply_text("\n".join(lines), reply_markup=get_worker_keyboard())
    else:
        c.execute(
            "SELECT w.name, COALESCE(SUM(s.price),0) as total FROM workers w "
            "LEFT JOIN services s ON w.id = s.worker_id AND s.date BETWEEN %s AND %s "
            "WHERE w.is_active = 1 GROUP BY w.name ORDER BY total DESC",
            (date_from, date_to)
        )
        rows = c.fetchall()
        conn.close()
        total_all = sum(r[1] for r in rows)
        _, owner_total = calc_percent(total_all)
        lines = [f"📊 {label} hisoboti\n"]
        for row in rows:
            name, total = row
            _, o_share = calc_percent(total)
            lines.append(f"👤 {name}: {format_money(total)} → Egasiga: {format_money(o_share)}")
        lines.append("")
        lines.append("─" * 25)
        lines.append(f"💰 Umumiy: {format_money(total_all)}")
        lines.append(f"👑 Egasiga: {format_money(owner_total)}")
        await update.message.reply_text("\n".join(lines), reply_markup=get_admin_keyboard())

async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    state = admin_state.get(user_id)

    # ── Asosiy tugmalar har doim ishlaydi ──
    MAIN_BUTTONS = [
        "📊 Umumiy hisobot", "👥 Masterlar", "➕ Xodim qo'shish",
        "❌ Xodim o'chirish", "📅 Dam olish kuni belgilash", "🗓 Dam olishni bekor qilish",
        "🏆 Eng yaxshi master", "💸 Oylik maosh", "💬 Xodimga xabar", "📢 Hammaga xabar",
        "📖 Yo'riqnoma", "📅 Qabullar", "📅 Ertangi qabullar"
    ]
    if text in MAIN_BUTTONS:
        admin_state.pop(user_id, None)
        state = None

    # ── Xodim qo'shish jarayoni ──
    if state == "waiting_worker_id":
        try:
            tid = int(text.strip())
            admin_state[user_id] = {"step": "waiting_name", "tid": tid}
            await update.message.reply_text("Xodimning ismini kiriting:")
        except:
            await update.message.reply_text("❌ Faqat Telegram ID (raqam) kiriting!")
        return

    if isinstance(state, dict) and state.get("step") == "waiting_name":
        name = text.strip()
        tid = state["tid"]
        result = add_worker(tid, name)
        admin_state.pop(user_id)
        if result:
            await update.message.reply_text(
                f"✅ {name} qo'shildi!\nTelegram ID: {tid}",
                reply_markup=get_admin_keyboard()
            )
        else:
            await update.message.reply_text("⚠️ Bu ID allaqachon mavjud.", reply_markup=get_admin_keyboard())
        return

    if state == "waiting_remove_id":
        try:
            tid = int(text.strip())
            remove_worker(tid)
            admin_state.pop(user_id)
            await update.message.reply_text("✅ Xodim o'chirildi.", reply_markup=get_admin_keyboard())
        except:
            await update.message.reply_text("❌ Faqat Telegram ID (raqam) kiriting!")
        return

    if state == "waiting_holiday":
        try:
            date = datetime.strptime(text.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")
            set_holiday(date)
            admin_state.pop(user_id)
            await update.message.reply_text(
                f"✅ {text.strip()} dam olish kuni belgilandi.",
                reply_markup=get_admin_keyboard()
            )
        except:
            await update.message.reply_text("❌ Format: KK.OO.YYYY — masalan: 09.06.2025")
        return

    if isinstance(state, dict) and state.get("step") == "waiting_date_from":
        try:
            today_str = get_now().strftime("%Y-%m-%d")
            tomorrow_str = (get_now() + timedelta(days=1)).strftime("%Y-%m-%d")

            if len(text.strip()) == 7 and text.strip()[2] == ".":
                month, year = text.strip().split(".")
                from calendar import monthrange
                days_in_month = monthrange(int(year), int(month))[1]
                date_from = f"{year}-{month.zfill(2)}-01"
                date_to = f"{year}-{month.zfill(2)}-{str(days_in_month).zfill(2)}"
            else:
                d = datetime.strptime(text.strip(), "%d.%m.%Y")
                date_from = d.strftime("%Y-%m-%d")
                date_to = None

            if date_from >= tomorrow_str:
                await update.message.reply_text("❌ Kelajak sanani kiritib bo'lmaydi!")
                return

            admin_state[user_id] = {**state, "step": "waiting_date_to", "date_from": date_from}
            if date_to:
                await generate_custom_report(update, context, state, date_from, date_to)
                admin_state.pop(user_id)
            else:
                await update.message.reply_text("Tugash sanasini kiriting (KK.OO.YYYY):\nMasalan: 18.06.2026")
        except:
            await update.message.reply_text("❌ Format xato! OO.YYYY yoki KK.OO.YYYY kiriting")
        return

    if isinstance(state, dict) and state.get("step") == "waiting_date_to":
        try:
            today_str = get_now().strftime("%Y-%m-%d")
            tomorrow_str = (get_now() + timedelta(days=1)).strftime("%Y-%m-%d")
            try:
                d = datetime.strptime(text.strip(), "%d.%m.%Y")
            except ValueError:
                await update.message.reply_text("❌ Format xato! KK.OO.YYYY kiriting\nMasalan: 18.06.2026")
                return
            date_to = d.strftime("%Y-%m-%d")
            date_from = state["date_from"]

            if date_to >= tomorrow_str:
                await update.message.reply_text("❌ Kelajak sanani kiritib bo'lmaydi!")
                return
            if date_to < date_from:
                await update.message.reply_text("❌ Tugash sanasi boshlanish sanasidan kichik bo'lmasin!")
                return

            await generate_custom_report(update, context, state, date_from, date_to)
            admin_state.pop(user_id)
        except Exception as e:
            await update.message.reply_text("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")
        return

    if isinstance(state, dict) and state.get("step") == "waiting_client_name":
        admin_state[user_id] = {**state, "step": "waiting_client_time", "client_name": text.strip()}
        await update.message.reply_text(
            f"Vaqtni kiriting (HH:MM):\nMasalan: 14:30"
        )
        return

    if isinstance(state, dict) and state.get("step") == "waiting_client_time":
        try:
            datetime.strptime(text.strip(), "%H:%M")
            time_str = text.strip()
            worker_id = state["worker_id"]
            date_str = state["date"]
            label = state["label"]
            client_name = state["client_name"]
            add_appointment(worker_id, date_str, time_str, client_name)
            admin_state.pop(user_id)
            await update.message.reply_text(
                f"✅ Saqlandi!\n📅 {label.capitalize()}\n🕐 {time_str} — {client_name}",
                reply_markup=get_worker_keyboard()
            )
        except ValueError:
            await update.message.reply_text("❌ Format xato! HH:MM kiriting\nMasalan: 14:30")
        return

    if isinstance(state, dict) and state.get("step") == "waiting_admin_fix_price":
        try:
            price = int(text.replace(" ", "").replace(",", ""))
            worker_id = state["worker_id"]
            service_name = state["service_name"]
            add_service(worker_id, service_name, price)
            admin_state.pop(user_id)
            await update.message.reply_text(
                f"✅ Saqlandi!\n{service_name} — {format_money(price)}",
                reply_markup=get_admin_keyboard()
            )
        except ValueError:
            await update.message.reply_text("❌ Faqat raqam kiriting! Masalan: 70000")
        return

    if state == "waiting_broadcast":
        workers = get_all_workers()
        sent = 0
        for w in workers:
            try:
                await context.bot.send_message(chat_id=w["telegram_id"], text=f"📢 Admin xabari:\n\n{text}")
                sent += 1
            except:
                pass
        admin_state.pop(user_id)
        await update.message.reply_text(f"✅ {sent} ta xodimga xabar yuborildi!", reply_markup=get_admin_keyboard())
        return

    if isinstance(state, dict) and state.get("step") == "waiting_msg_text":
        tid = state["tid"]
        try:
            await context.bot.send_message(chat_id=tid, text=f"💬 Admin xabari:\n\n{text}")
            admin_state.pop(user_id)
            await update.message.reply_text("✅ Xabar yuborildi!", reply_markup=get_admin_keyboard())
        except:
            await update.message.reply_text("❌ Xabar yuborib bo'lmadi.")
        return

    if state == "waiting_remove_holiday":
        try:
            date = datetime.strptime(text.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")
            from database import get_conn
            conn = get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM work_days WHERE date = %s AND is_holiday = 1", (date,))
            conn.commit()
            conn.close()
            admin_state.pop(user_id)
            await update.message.reply_text(
                f"✅ {text.strip()} dam olish kuni bekor qilindi.",
                reply_markup=get_admin_keyboard()
            )
        except:
            await update.message.reply_text("❌ Format: KK.OO.YYYY — masalan: 09.06.2025")
        return

    # ── Asosiy admin tugmalari ──
    admin_state.pop(user_id, None)
    if text == "📊 Umumiy hisobot":
        await update.message.reply_text(
            "Hisobot davrini tanlang:",
            reply_markup=get_report_period_keyboard()
        )
        return

    if text == "👥 Masterlar":
        workers = get_all_workers()
        if not workers:
            await update.message.reply_text("Xodimlar yo'q.")
            return
        today = get_now().strftime("%Y-%m-%d")
        lines = ["👥 Masterlar holati:\n"]
        kb = []
        for w in workers:
            wd = get_work_day(w["id"], today)
            if wd and wd.get("is_holiday"):
                status = "🏖 Dam olish kuni"
            elif wd and wd.get("end_time"):
                status = f"✅ Yakunladi ({wd['start_time']} — {wd['end_time']})"
            elif wd and wd.get("start_time"):
                status = f"🟢 Ishlayapti ({wd['start_time']} dan beri)"
            else:
                status = "⭕ Hali boshlamadi"
            lines.append(f"👤 {w['name']}\n{status}")
            kb.append([InlineKeyboardButton(f"👤 {w['name']}", callback_data=f"worker_{w['telegram_id']}")])
        await update.message.reply_text(
            "\n\n".join(lines),
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if text == "➕ Xodim qo'shish":
        admin_state[user_id] = "waiting_worker_id"
        await update.message.reply_text("Yangi xodimning Telegram ID sini kiriting:")
        return

    if text == "❌ Xodim o'chirish":
        admin_state[user_id] = "waiting_remove_id"
        await update.message.reply_text("O'chiriladigan xodimning Telegram ID sini kiriting:")
        return

    if text == "📅 Dam olish kuni belgilash":
        admin_state[user_id] = "waiting_holiday"
        await update.message.reply_text("Dam olish kunini kiriting (KK.OO.YYYY):\nMasalan: 09.06.2025")
        return

    if text == "🗓 Dam olishni bekor qilish":
        admin_state[user_id] = "waiting_remove_holiday"
        await update.message.reply_text("Bekor qilinadigan sanani kiriting (KK.OO.YYYY):\nMasalan: 09.06.2025")
        return

    if text == "📅 Qabullar":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Bugungi qabullar", callback_data="admin_appt_today"),
             InlineKeyboardButton("📅 Ertangi qabullar", callback_data="admin_appt_tomorrow")]
        ])
        await update.message.reply_text("Qaysi kunni ko'rmoqchisiz?", reply_markup=kb)
        return

    if text == "📖 Yo'riqnoma":
        await update.message.reply_text(
            "📖 Admin yo'riqnomasi\n\n"
            "👥 Masterlar — Xodimlar holati (kim kelgan, kim kelmagan, kim yakunlagan)\n\n"
            "📊 Umumiy hisobot — Davr bo'yicha barcha xodimlar hisoboti\n"
            "🏆 Eng yaxshi master — Haftalik yoki oylik reyting\n"
            "💸 Oylik maosh — Har bir xodimning 30 kunlik daromadi (70%)\n\n"
            "💬 Xodimga xabar — Bitta xodimga botdan xabar yuborish\n"
            "📢 Hammaga xabar — Barcha xodimlarga bir vaqtda xabar yuborish\n\n"
            "📅 Dam olish kuni belgilash — O'sha kuni xodimlar ishlamaydi\n"
            "🗓 Dam olishni bekor qilish — Dam olish kunini olib tashlash\n\n"
            "➕ Xodim qo'shish — Yangi xodim Telegram ID si va ismini kiriting\n"
            "❌ Xodim o'chirish — Xodimni tizimdan o'chirish\n\n"
            "🏢 Biznes almashtirish — Boshqa biznesga o'tish",
            reply_markup=get_admin_keyboard()
        )
        return

    if text == "🏆 Eng yaxshi master":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Bu hafta", callback_data="top_7"),
             InlineKeyboardButton("Bu oy", callback_data="top_30")],
        ])
        await update.message.reply_text("Qaysi davr?", reply_markup=kb)
        return

    if text == "💸 Oylik maosh":
        workers = get_all_workers_summary_range(30)
        lines = ["💸 Oylik maosh hisobi (30 kun)\n"]
        for w in workers:
            total = w["total"] or 0
            w_share, _ = calc_percent(total)
            lines.append(f"👤 {w['name']}: {format_money(w_share)}")
        await update.message.reply_text("\n".join(lines), reply_markup=get_admin_keyboard())
        return

    if text == "💬 Xodimga xabar":
        workers = get_all_workers()
        if not workers:
            await update.message.reply_text("Xodimlar yo'q.")
            return
        kb = [[InlineKeyboardButton(f"👤 {w['name']}", callback_data=f"msgto_{w['telegram_id']}")] for w in workers]
        await update.message.reply_text("Kimga xabar yubormoqchisiz?", reply_markup=InlineKeyboardMarkup(kb))
        return

    if text == "📢 Hammaga xabar":
        admin_state[user_id] = "waiting_broadcast"
        await update.message.reply_text("Barcha xodimlarga yuboriladigan xabarni kiriting:")
        return

# ─── CALLBACKS ───

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # ── Amoria Bar callbacklari ──
    if query.data and query.data.startswith("am_"):
        await handle_amoria_callback(update, context)
        return

    if query.data and query.data.startswith("dr_"):
        await handle_dress_callback(update, context)
        return

    await query.answer()
    data = query.data

    if data == "endday_cancel":
        await query.edit_message_text("❌ Yakunlash bekor qilindi.")
        return

    if data.startswith("endday_"):
        worker_id = int(data.split("_")[1])
        result = end_work_day(worker_id)
        if not result:
            await query.edit_message_text("⚠️ Xatolik yuz berdi.")
            return

        today = get_now().strftime("%Y-%m-%d")
        services = get_services_by_worker_date(worker_id, today)
        total = sum(s["total"] for s in services)
        worker_share, owner_share = calc_percent(total)

        from database import get_conn
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT name FROM workers WHERE id = %s", (worker_id,))
        w = cur.fetchone()
        conn.close()
        wname = w[0] if w else "Xodim"

        lines = [f"✅ {wname} ish kunini yakunladi"]
        lines.append(f"🕐 {result['start']} — {result['end']}")

        try:
            fmt = "%H:%M"
            delta = datetime.strptime(result["end"], fmt) - datetime.strptime(result["start"], fmt)
            h, m = divmod(int(delta.total_seconds()) // 60, 60)
            lines.append(f"⏱ Ish vaqti: {h} soat {m} daqiqa")
        except:
            pass

        lines.append("")
        lines.append("📋 Xizmatlar:")
        for s in services:
            lines.append(f"  {s['service_name']} × {s['cnt']} — {format_money(s['total'])}")
        lines.append("")
        lines.append("─" * 25)
        lines.append(f"💰 Jami: {format_money(total)}")
        lines.append(f"👤 {wname} (70%): {format_money(worker_share)}")
        lines.append(f"👑 Egasiga (30%): {format_money(owner_share)}")

        msg = "\n".join(lines)
        await query.edit_message_text(msg)
        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=aid, text=f"🔔 {msg}")
            except:
                pass
        return

    if data.startswith("report_") and not data.endswith("_custom"):
        days = int(data.split("_")[1])
        label = {1: "1 kunlik", 3: "3 kunlik", 7: "7 kunlik", 15: "15 kunlik", 30: "1 oylik"}[days]

        workers = get_all_workers_summary_range(days)
        total_all = sum(w["total"] or 0 for w in workers)
        _, owner_total = calc_percent(total_all)

        lines = [f"📊 {label} hisobot"]
        lines.append(f"📅 So'nggi {days} kun\n")

        for w in workers:
            total = w["total"] or 0
            w_share, o_share = calc_percent(total)
            lines.append(f"👤 {w['name']}: {format_money(total)} → Egasiga: {format_money(o_share)}")

            summaries = get_worker_summary_range(w["id"], days)
            work_days_data = {}
            for s in summaries:
                work_days_data[s["date"]] = s["total"]

            for day_row in summaries:
                d = datetime.strptime(day_row["date"], "%Y-%m-%d").strftime("%d.%m")
                wd = None
                lines.append(f"  📅 {d} — {format_money(day_row['total'])}")

        lines.append("")
        lines.append("─" * 25)
        lines.append(f"💰 Umumiy jami: {format_money(total_all)}")
        lines.append(f"👑 Egasiga jami (30%): {format_money(owner_total)}")

        await query.edit_message_text("\n".join(lines))
        return

    if data.startswith("worker_"):
        tid = int(data.split("_")[1])
        worker = get_worker(tid)
        if not worker:
            await query.edit_message_text("Xodim topilmadi.")
            return

        today = get_now().strftime("%Y-%m-%d")
        wd = get_work_day(worker["id"], today)
        
        kb = [
            [InlineKeyboardButton("1 kun", callback_data=f"wreport_{tid}_1"),
             InlineKeyboardButton("3 kun", callback_data=f"wreport_{tid}_3")],
            [InlineKeyboardButton("7 kun", callback_data=f"wreport_{tid}_7"),
             InlineKeyboardButton("15 kun", callback_data=f"wreport_{tid}_15")],
            [InlineKeyboardButton("1 oy", callback_data=f"wreport_{tid}_30")],
        ]
        
        # Show restart and edit buttons if worker ended their day
        if wd and wd.get("end_time"):
            kb.append([InlineKeyboardButton("🔄 Qayta boshlash ruxsati", callback_data=f"restart_{tid}")])
            kb.append([InlineKeyboardButton("🔧 Xizmatni tuzatish", callback_data=f"adminfix_{tid}")])
        
        await query.edit_message_text(
            f"👤 {worker['name']} — davr tanlang:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if data == "delservice_cancel":
        await query.edit_message_text("❌ Bekor qilindi.")
        return

    if data.startswith("delservice_"):
        parts = data.split("_")
        service_id = int(parts[1])
        worker_id = int(parts[2])

        from database import get_conn
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT service_name, price FROM services WHERE id = %s", (service_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            await query.edit_message_text("⚠️ Yozuv topilmadi.")
            return
        sname, sprice = row
        c.execute("DELETE FROM services WHERE id = %s", (service_id,))
        conn.commit()
        conn.close()

        # Ask to re-enter
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ha, qayta kiritaman", callback_data=f"reenter_{worker_id}_{sname}"),
             InlineKeyboardButton("❌ Yo'q", callback_data="reenter_cancel")]
        ])
        await query.edit_message_text(
            f"✅ O'chirildi: {sname} — {format_money(sprice)}\n\nQayta kiritasizmi?",
            reply_markup=kb
        )
        return

    if data == "reenter_cancel":
        await query.edit_message_text("✅ O'chirildi.")
        return

    if data.startswith("reenter_"):
        parts = data.split("_", 2)
        worker_id = int(parts[1])
        sname = parts[2]
        pending_service[query.from_user.id] = sname
        await query.edit_message_text(f"{sname} uchun yangi narxni kiriting (so'm):")
        return

    if data.endswith("_custom"):
        prefix = data.replace("_custom", "")
        user_id = query.from_user.id
        if prefix.startswith("myreport_"):
            worker_id = int(prefix.split("_")[1])
            admin_state[user_id] = {"step": "waiting_date_from", "type": "worker", "worker_id": worker_id}
            await query.edit_message_text(
                "Oyni (OO.YYYY) yoki boshlanish sanasini (KK.OO.YYYY) kiriting:\n"
                "Masalan: 05.2026 yoki 01.05.2026"
            )
        else:
            admin_state[user_id] = {"step": "waiting_date_from", "type": "admin"}
            await query.edit_message_text(
                "Oyni (OO.YYYY) yoki boshlanish sanasini (KK.OO.YYYY) kiriting:\n"
                "Masalan: 05.2026 yoki 01.05.2026"
            )
        return

    if data.startswith("top_"):
        days = int(data.split("_")[1])
        label = "haftalik" if days == 7 else "oylik"
        workers = get_all_workers_summary_range(days)
        if not workers:
            await query.edit_message_text("Ma'lumot yo'q.")
            return
        lines = [f"🏆 Eng yaxshi master — {label}\n"]
        for i, w in enumerate(workers, 1):
            total = w["total"] or 0
            medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
            lines.append(f"{medal} {w['name']}: {format_money(total)}")
        await query.edit_message_text("\n".join(lines))
        return

    if data.startswith("msgto_"):
        tid = int(data.split("_")[1])
        from database import get_conn, dict_row as _dr
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT name FROM workers WHERE telegram_id = %s", (tid,))
        row = c.fetchone()
        conn.close()
        name = row[0] if row else "Xodim"
        admin_id = query.from_user.id
        admin_state[admin_id] = {"step": "waiting_msg_text", "tid": tid}
        await query.edit_message_text(f"💬 {name} ga xabar kiriting:")
        return

    if data.startswith("myreport_"):
        parts = data.split("_")
        worker_id = int(parts[1])
        days_str = parts[2]
        if days_str == "custom":
            return
        days = int(days_str)

        from database import get_conn, dict_row as _dict_row
        wconn = get_conn()
        wcur = wconn.cursor()
        wcur.execute("SELECT * FROM workers WHERE id = %s", (worker_id,))
        wrow = wcur.fetchone()
        wconn.close()
        if not wrow:
            await query.edit_message_text("Xodim topilmadi.")
            return
        worker_data = _dict_row(wcur, wrow)

        if days == 0:
            # Bugun
            today = get_now().strftime("%Y-%m-%d")
            services = get_services_by_worker_date(worker_id, today)
            total = sum(s["total"] for s in services)
            worker_share, _ = calc_percent(total)
            work_day = get_work_day(worker_id, today)

            lines = [f"📊 {worker_data['name']} — Bugungi hisobot"]
            lines.append(f"📅 {get_now().strftime('%d.%m.%Y')}")
            if work_day and work_day.get("start_time"):
                if work_day.get("end_time"):
                    lines.append(f"🕐 {work_day['start_time']} — {work_day['end_time']}")
                else:
                    lines.append(f"🕐 Boshlash: {work_day['start_time']}")
            lines.append("")
            if services:
                for s in services:
                    lines.append(f"{s['service_name']} × {s['cnt']} — {format_money(s['total'])}")
                lines.append("")
                lines.append("─" * 25)
                lines.append(f"💰 Jami: {format_money(total)}")
                lines.append(f"👤 Sizniki (70%): {format_money(worker_share)}")
            else:
                lines.append("Bugun hali xizmat kiritilmagan.")
        else:
            # Ko'p kunlik
            services = get_services_by_worker_range(worker_id, days)
            summaries = get_worker_summary_range(worker_id, days)
            label = {3: "3 kunlik", 7: "7 kunlik", 15: "15 kunlik", 30: "1 oylik"}[days]

            lines = [f"📊 {worker_data['name']} — {label} hisobot\n"]
            by_date = {}
            for s in services:
                by_date.setdefault(s["date"], []).append(s)

            total_all = 0
            for date_str in sorted(by_date.keys(), reverse=True):
                d = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
                day_services = by_date[date_str]
                day_total = sum(s["total"] for s in day_services)
                total_all += day_total
                w_share, _ = calc_percent(day_total)
                lines.append(f"📅 {d}")
                for s in day_services:
                    lines.append(f"  {s['service_name']} × {s['cnt']} — {format_money(s['total'])}")
                lines.append(f"  💰 {format_money(day_total)} | 👤 Sizniki: {format_money(w_share)}")
                lines.append("")

            total_share, _ = calc_percent(total_all)
            lines.append("─" * 25)
            lines.append(f"💰 Jami: {format_money(total_all)}")
            lines.append(f"👤 Sizniki (70%): {format_money(total_share)}")

        await query.edit_message_text("\n".join(lines))
        return

    if data in ["admin_appt_today", "admin_appt_tomorrow"]:
        if data == "admin_appt_today":
            date_str = get_now().strftime("%Y-%m-%d")
            label = get_now().strftime("%d.%m.%Y")
            title = "Bugungi"
        else:
            date_str = (get_now() + timedelta(days=1)).strftime("%Y-%m-%d")
            label = (get_now() + timedelta(days=1)).strftime("%d.%m.%Y")
            title = "Ertangi"
        rows = get_all_appointments(date_str)
        if not rows:
            await query.edit_message_text(f"📅 {title} qabullar ({label}) yo'q.")
        else:
            lines = [f"📅 {title} qabullar — {label}\n"]
            for row in rows:
                lines.append(f"🕐 {row[2]} — {row[3]} ({row[1]})")
            await query.edit_message_text("\n".join(lines))
        return

    if data.startswith("appt_new_"):
        parts = data.split("_")
        worker_id = int(parts[2])
        day = parts[3]
        if day == "today":
            date_str = get_now().strftime("%Y-%m-%d")
            label = "bugun"
        else:
            date_str = (get_now() + timedelta(days=1)).strftime("%Y-%m-%d")
            label = "ertaga"
        admin_state[query.from_user.id] = {
            "step": "waiting_client_name",
            "worker_id": worker_id,
            "date": date_str,
            "label": label
        }
        await query.edit_message_text(f"📅 {label.capitalize()} uchun mijoz ismini kiriting:")
        return

    if data.startswith("appt_list_"):
        parts = data.split("_")
        worker_id = int(parts[2])
        day = parts[3]
        if day == "today":
            date_str = get_now().strftime("%Y-%m-%d")
            label = "Bugungi"
        else:
            date_str = (get_now() + timedelta(days=1)).strftime("%Y-%m-%d")
            label = "Ertangi"
        rows = get_appointments(worker_id, date_str)
        if not rows:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data=f"appt_back_{worker_id}")]])
            await query.edit_message_text(f"📅 {label} qabullar yo'q.", reply_markup=kb)
            return
        lines = [f"📅 {label} qabullar:\n"]
        kb = []
        for row in rows:
            lines.append(f"🕐 {row[1]} — {row[2]}")
            kb.append([InlineKeyboardButton(f"❌ {row[1]} — {row[2]}", callback_data=f"appt_del_{row[0]}_{worker_id}_{day}")])
        kb.append([InlineKeyboardButton("🔙 Orqaga", callback_data=f"appt_back_{worker_id}")])
        await query.edit_message_text("\n".join(lines) + "\n\nO'chirish uchun bosing:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("appt_del_"):
        parts = data.split("_")
        appt_id = int(parts[2])
        worker_id = int(parts[3])
        day = parts[4]
        delete_appointment(appt_id)
        await query.answer("✅ O'chirildi!")
        # Refresh list
        if day == "today":
            date_str = get_now().strftime("%Y-%m-%d")
            label = "Bugungi"
        else:
            date_str = (get_now() + timedelta(days=1)).strftime("%Y-%m-%d")
            label = "Ertangi"
        rows = get_appointments(worker_id, date_str)
        if not rows:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data=f"appt_back_{worker_id}")]])
            await query.edit_message_text(f"📅 {label} qabullar yo'q.", reply_markup=kb)
            return
        lines = [f"📅 {label} qabullar:\n"]
        kb = []
        for row in rows:
            lines.append(f"🕐 {row[1]} — {row[2]}")
            kb.append([InlineKeyboardButton(f"❌ {row[1]} — {row[2]}", callback_data=f"appt_del_{row[0]}_{worker_id}_{day}")])
        kb.append([InlineKeyboardButton("🔙 Orqaga", callback_data=f"appt_back_{worker_id}")])
        await query.edit_message_text("\n".join(lines) + "\n\nO'chirish uchun bosing:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("appt_back_"):
        worker_id = int(data.split("_")[2])
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Bugun", callback_data=f"appt_new_{worker_id}_today"),
             InlineKeyboardButton("📅 Ertaga", callback_data=f"appt_new_{worker_id}_tomorrow")],
            [InlineKeyboardButton("📋 Bugungi qabullar", callback_data=f"appt_list_{worker_id}_today"),
             InlineKeyboardButton("📋 Ertangi qabullar", callback_data=f"appt_list_{worker_id}_tomorrow")],
        ])
        await query.edit_message_text("📅 Mijoz qabul:", reply_markup=kb)
        return

    if data.startswith("adminfix_"):
        tid = int(data.split("_")[1])
        worker = get_worker(tid)
        if not worker:
            await query.edit_message_text("Xodim topilmadi.")
            return
        today = get_now().strftime("%Y-%m-%d")
        from database import get_conn
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT id, service_name, price, created_at FROM services "
            "WHERE worker_id = %s AND date = %s ORDER BY id",
            (worker["id"], today)
        )
        rows = c.fetchall()
        conn.close()
        if not rows:
            await query.edit_message_text("Bugun xizmat kiritilmagan.")
            return
        kb = []
        for row in rows:
            sid, sname, sprice, screated = row
            time_str = screated[11:16] if screated and len(screated) > 11 else ""
            kb.append([InlineKeyboardButton(
                f"❌ {sname} — {format_money(sprice)} ({time_str})",
                callback_data=f"admindel_{sid}_{tid}"
            )])
        kb.append([InlineKeyboardButton("🔙 Orqaga", callback_data=f"worker_{tid}")])
        await query.edit_message_text(
            f"👤 {worker['name']} — bugungi xizmatlar\nO'chirish uchun bosing:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if data.startswith("admindel_"):
        parts = data.split("_")
        service_id = int(parts[1])
        tid = int(parts[2])
        from database import get_conn
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT service_name, price FROM services WHERE id = %s", (service_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            await query.edit_message_text("Xizmat topilmadi.")
            return
        sname, sprice = row
        c.execute("DELETE FROM services WHERE id = %s", (service_id,))
        conn.commit()
        conn.close()

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ha, qayta kiriting", callback_data=f"adminreenter_{tid}_{sname}_{sprice}"),
             InlineKeyboardButton("❌ Yo'q", callback_data=f"adminfix_{tid}")]
        ])
        await query.edit_message_text(
            f"✅ O'chirildi: {sname} — {format_money(sprice)}\n\nQayta kiritasizmi?",
            reply_markup=kb
        )
        return

    if data.startswith("adminreenter_"):
        parts = data.split("_", 3)
        tid = int(parts[1])
        sname = parts[2]
        worker = get_worker(tid)
        if not worker:
            await query.edit_message_text("Xodim topilmadi.")
            return
        admin_state[query.from_user.id] = {
            "step": "waiting_admin_fix_price",
            "worker_id": worker["id"],
            "service_name": sname
        }
        await query.edit_message_text(
            f"👤 {worker['name']} uchun\n{sname} — yangi narxni kiriting (so'm):"
        )
        return

    if data.startswith("restart_"):
        tid = int(data.split("_")[1])
        worker = get_worker(tid)
        if not worker:
            await query.edit_message_text("Xodim topilmadi.")
            return
        session = allow_restart(worker["id"])
        await query.edit_message_text(
            f"✅ {worker['name']} ga qayta boshlash ruxsati berildi!\n"
            f"🔄 {session}-session boshlandi."
        )
        try:
            await context.bot.send_message(
                chat_id=tid,
                text=f"✅ Admin ruxsat berdi! Ish davom ettirishingiz mumkin.\n🕐 {get_now().strftime('%H:%M')} dan boshlanadi."
            )
        except:
            pass
        return

    if data.startswith("wreport_"):
        parts = data.split("_")
        tid = int(parts[1])
        days = int(parts[2])

        worker = get_worker(tid)
        if not worker:
            await query.edit_message_text("Xodim topilmadi.")
            return

        services = get_services_by_worker_range(worker["id"], days)
        summaries = get_worker_summary_range(worker["id"], days)

        label = {1: "1 kunlik", 3: "3 kunlik", 7: "7 kunlik", 15: "15 kunlik", 30: "1 oylik"}[days]
        lines = [f"👤 {worker['name']} — {label} hisobot\n"]

        by_date = {}
        for s in services:
            by_date.setdefault(s["date"], []).append(s)

        total_all = 0
        for date_str in sorted(by_date.keys(), reverse=True):
            d = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
            day_services = by_date[date_str]
            day_total = sum(s["total"] for s in day_services)
            total_all += day_total

            wd = None
            from database import get_conn
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT start_time, end_time FROM work_days WHERE worker_id = %s AND date = %s",
                (worker["id"], date_str)
            )
            wd_row = cur.fetchone()
            wd = {"start_time": wd_row[0], "end_time": wd_row[1]} if wd_row else None
            conn.close()

            time_info = ""
            if wd and wd["start_time"]:
                time_info = f" | 🕐 {wd['start_time']}"
                if wd["end_time"]:
                    time_info += f" — {wd['end_time']}"

            # Get sessions for this day
            sessions = get_all_sessions(worker["id"], date_str)
            session_info = ""
            if len(sessions) > 1:
                for s in sessions:
                    if s.get("start_time"):
                        end = s["end_time"] or "..."
                        session_info += f"\n  🔄 {s['session']}-session: {s['start_time']} — {end}"
            elif sessions and sessions[0].get("start_time"):
                end = sessions[0]["end_time"] or "..."
                session_info = f" | 🕐 {sessions[0]['start_time']} — {end}"

            lines.append(f"📅 {d}{session_info}")
            for s in day_services:
                lines.append(f"  {s['service_name']} × {s['cnt']} — {format_money(s['total'])}")
            w_share, o_share = calc_percent(day_total)
            lines.append(f"  💰 {format_money(day_total)} | 👑 {format_money(o_share)}")
            lines.append("")

        w_total, o_total = calc_percent(total_all)
        lines.append("─" * 25)
        lines.append(f"💰 Jami: {format_money(total_all)}")
        lines.append(f"👤 {worker['name']} (70%): {format_money(w_total)}")
        lines.append(f"👑 Egasiga (30%): {format_money(o_total)}")

        await query.edit_message_text("\n".join(lines))
        return

# ─── SCHEDULED JOBS ───

async def auto_close_days(context: ContextTypes.DEFAULT_TYPE):
    from database import get_conn
    yesterday = (get_now() - timedelta(days=1)).strftime("%Y-%m-%d")
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE work_days SET end_time = '23:59' WHERE date = %s AND start_time IS NOT NULL AND end_time IS NULL",
        (yesterday,)
    )
    conn.commit()
    conn.close()

async def morning_greeting(context: ContextTypes.DEFAULT_TYPE):
    workers = get_all_workers()
    for w in workers:
        try:
            await context.bot.send_message(
                chat_id=w["telegram_id"],
                text="☀️ Xayrli tong! Kunni boshlashni unutmang! 💈"
            )
        except:
            pass
    for aid in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=aid,
                text="☀️ Xayrli tong Behruz aka!\nSoqqani bosaylik, endi masterlarni kuzatib boring! 💈"
            )
        except:
            pass

async def reminder_not_started(context: ContextTypes.DEFAULT_TYPE):
    workers = workers_not_started()
    for w in workers:
        try:
            await context.bot.send_message(
                chat_id=w["telegram_id"],
                text="⏰ Eslatma: Kunni boshlashni unutmadingizmi? '🌅 Kunni boshlash' ni bosing!"
            )
        except:
            pass

async def reminder_not_ended(context: ContextTypes.DEFAULT_TYPE):
    workers_list = workers_not_ended()
    for w in workers_list:
        try:
            await context.bot.send_message(
                chat_id=w["telegram_id"],
                text="⏰ Eslatma: Kunni yakunladingizmi? '✅ Kunni yakunlash' ni bosing!"
            )
        except:
            pass

# ─── MAIN ───

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_service))
    app.add_handler(CallbackQueryHandler(callback_handler))

    jq = app.job_queue
    jq.run_daily(auto_close_days, time=dtime(0, 1, tzinfo=TZ))
    jq.run_daily(morning_greeting, time=dtime(9, 0, tzinfo=TZ))
    jq.run_daily(reminder_not_started, time=dtime(10, 0, tzinfo=TZ))
    jq.run_daily(reminder_not_ended, time=dtime(20, 0, tzinfo=TZ))

    print("Bot ishga tushdi! ✅")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == "__main__":
    main()
