import os
import asyncio
from datetime import datetime, timezone, timedelta
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
    start_work_day, end_work_day, get_work_day,
    add_service, delete_last_service, get_services_by_worker_date,
    get_services_by_worker_range, get_worker_summary_range,
    get_all_workers_summary_range, get_today_summary_all,
    workers_not_started, workers_not_ended, set_holiday,
    SERVICE_NAMES
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

STICKER_LAUGH = "CAACAgIAAxkBAAIBv2RtQkLbMnY1oqRzvXBHJJGpuHmVAAIUAANWnb0KODBFMQbMrUsvBA"

ENTER_PRICE, ENTER_WORKER_ID, ENTER_WORKER_NAME, ENTER_REMOVE_ID, ENTER_HOLIDAY = range(5)

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def format_money(amount) -> str:
    if amount is None:
        amount = 0
    return f"{int(amount):,}".replace(",", " ") + " so'm"

def calc_percent(total):
    worker = int(total * 0.7)
    owner = int(total * 0.3)
    return worker, owner

def get_worker_keyboard():
    kb = [
        [KeyboardButton("✂️ Soch olish"), KeyboardButton("🚿 Soch yuvish")],
        [KeyboardButton("🪒 Soqol olish"), KeyboardButton("👰 Kiyov tayyorlash")],
        [KeyboardButton("💆 Yuz tozalash"), KeyboardButton("🎭 Maska")],
        [KeyboardButton("🎨 Soch bo'yash"), KeyboardButton("📊 Hisobotim")],
        [KeyboardButton("🌅 Kunni boshlash"), KeyboardButton("✅ Kunni yakunlash")],
        [KeyboardButton("🗑 Oxirgini o'chir"), KeyboardButton("👑 Admin panel")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def get_admin_keyboard():
    kb = [
        [KeyboardButton("📊 Umumiy hisobot"), KeyboardButton("👥 Masterlar")],
        [KeyboardButton("➕ Xodim qo'shish"), KeyboardButton("❌ Xodim o'chirish")],
        [KeyboardButton("📅 Dam olish kuni belgilash")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def get_report_period_keyboard():
    kb = [
        [InlineKeyboardButton("1 kunlik", callback_data="report_1"),
         InlineKeyboardButton("3 kunlik", callback_data="report_3")],
        [InlineKeyboardButton("7 kunlik", callback_data="report_7"),
         InlineKeyboardButton("15 kunlik", callback_data="report_15")],
        [InlineKeyboardButton("1 oylik", callback_data="report_30")],
    ]
    return InlineKeyboardMarkup(kb)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if is_admin(user_id):
        await update.message.reply_text(
            "👑 Xush kelibsiz, Behruz aka!\nSoqqani bosaylik! 💈",
            reply_markup=get_admin_keyboard()
        )
        return

    worker = get_worker(user_id)
    if worker:
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
        await handle_admin_message(update, context)
        return

    worker = get_worker(user_id)
    if not worker:
        await update.message.reply_text("❌ Siz tizimda yo'qsiz.")
        return

    today = get_now().strftime("%Y-%m-%d")
    work_day = get_work_day(worker["id"], today)

    # ── Kunni boshlash ──
    if text == "🌅 Kunni boshlash":
        result = start_work_day(worker["id"])
        if result:
            current_time_str = get_now().strftime("%H:%M")
            await update.message.reply_text(
                f"✅ Ish kuni boshlandi!\n🕐 Boshlash vaqti: {current_time_str}",
                reply_markup=get_worker_keyboard()
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

        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 {msg}")
        except:
            pass
        return

    # ── Hisobotim ──
    if text == "📊 Hisobotim":
        services = get_services_by_worker_date(worker["id"], today)
        total = sum(s["total"] for s in services)
        worker_share, owner_share = calc_percent(total)

        work_day = get_work_day(worker["id"], today)
        lines = [f"📊 {worker['name']} — Bugungi hisobot"]
        lines.append(f"📅 {get_now().strftime('%d.%m.%Y')}")
        if work_day and work_day["start_time"]:
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

        await update.message.reply_text("\n".join(lines), reply_markup=get_worker_keyboard())
        return

    # ── Oxirgini o'chir ──
    if text == "🗑 Oxirgini o'chir":
        result = delete_last_service(worker["id"])
        if result:
            await update.message.reply_text("✅ Oxirgi yozuv o'chirildi.", reply_markup=get_worker_keyboard())
        else:
            await update.message.reply_text("⚠️ O'chiriladigan yozuv topilmadi.", reply_markup=get_worker_keyboard())
        return

    # ── Admin panel (xodim bosadi) ──
    if text == "👑 Admin panel":
        await update.message.reply_text(
            "👑 Bu bo'lim faqat Behruz aka uchun!\nSiz esa master! 😄"
        )
        await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=STICKER_LAUGH)
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

async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    state = admin_state.get(user_id)

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

    # ── Asosiy admin tugmalari ──
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
        kb = [[InlineKeyboardButton(f"👤 {w['name']}", callback_data=f"worker_{w['telegram_id']}")] for w in workers]
        await update.message.reply_text(
            "Xodimni tanlang:",
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

# ─── CALLBACKS ───

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
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
        w = conn.execute("SELECT name FROM workers WHERE id = ?", (worker_id,)).fetchone()
        conn.close()
        wname = w["name"] if w else "Xodim"

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
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 {msg}")
        except:
            pass
        return

    if data.startswith("report_"):
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

        kb = [
            [InlineKeyboardButton("1 kun", callback_data=f"wreport_{tid}_1"),
             InlineKeyboardButton("3 kun", callback_data=f"wreport_{tid}_3")],
            [InlineKeyboardButton("7 kun", callback_data=f"wreport_{tid}_7"),
             InlineKeyboardButton("15 kun", callback_data=f"wreport_{tid}_15")],
            [InlineKeyboardButton("1 oy", callback_data=f"wreport_{tid}_30")],
        ]
        await query.edit_message_text(
            f"👤 {worker['name']} — davr tanlang:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
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
            wd = conn.execute(
                "SELECT start_time, end_time FROM work_days WHERE worker_id = ? AND date = ?",
                (worker["id"], date_str)
            ).fetchone()
            conn.close()

            time_info = ""
            if wd and wd["start_time"]:
                time_info = f" | 🕐 {wd['start_time']}"
                if wd["end_time"]:
                    time_info += f" — {wd['end_time']}"

            lines.append(f"📅 {d}{time_info}")
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
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
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

async def evening_admin_report(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text="🌙 Behruz aka, soqqa ko'payib ketdi!\nPullarni ko'ring! 💰😄"
        )
    except:
        pass

    summary = get_today_summary_all()
    total_all = sum(w["total"] or 0 for w in summary)
    _, owner_total = calc_percent(total_all)

    today = get_now().strftime("%d.%m.%Y")
    lines = [f"📊 Kun yakunlandi — {today}\n"]

    for w in summary:
        total = w["total"] or 0
        _, o_share = calc_percent(total)
        worker_id = w["id"]

        from database import get_services_by_worker_date
        services = get_services_by_worker_date(worker_id, get_now().strftime("%Y-%m-%d"))

        time_info = ""
        if w["start_time"]:
            time_info = f"\n🕐 {w['start_time']}"
            if w["end_time"]:
                time_info += f" — {w['end_time']}"

        lines.append(f"👤 {w['name']}{time_info}")
        for s in services:
            lines.append(f"  {s['service_name']} × {s['cnt']} — {format_money(s['total'])}")
        lines.append(f"  💰 Jami: {format_money(total)} | 👑 Egasiga: {format_money(o_share)}")
        lines.append("")

    lines.append("─" * 25)
    lines.append(f"💰 Umumiy: {format_money(total_all)}")
    lines.append(f"👑 Egasiga jami: {format_money(owner_total)}")

    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text="\n".join(lines))
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
    jq.run_daily(morning_greeting, time=datetime.strptime("09:00", "%H:%M").time())
    jq.run_daily(reminder_not_started, time=datetime.strptime("10:00", "%H:%M").time())
    jq.run_daily(reminder_not_ended, time=datetime.strptime("20:00", "%H:%M").time())
    jq.run_daily(evening_admin_report, time=datetime.strptime("21:00", "%H:%M").time())

    print("Bot ishga tushdi! ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
