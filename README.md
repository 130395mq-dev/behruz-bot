# 💈 Barbershop Bot

Barbershop uchun Telegram hisob-kitob boti.

---

## 🚀 Ishga tushirish

### 1. BotFather dan token oling
1. Telegramda @BotFather ga yozing
2. `/newbot` bosing
3. Bot nomini kiriting
4. Token olasiz — uni saqlang

### 2. O'z Telegram ID ingizni toping
@userinfobot ga `/start` yuboring — ID chiqadi

### 3. `.env` fayl yarating
```
cp .env.example .env
```
`.env` faylni oching va to'ldiring:
```
BOT_TOKEN=7xxxxxxxxx:AAxxxxxxxxxxxxxxxxxxxxxxxx
ADMIN_ID=123456789
```

### 4. GitHub ga yuklang
```bash
git init
git add .
git commit -m "first commit"
git remote add origin https://github.com/sizning_username/barbershop-bot.git
git push -u origin main
```

### 5. Railway ga deploy qiling
1. railway.app ga kiring
2. "New Project" → "Deploy from GitHub repo"
3. Repo ni tanlang
4. "Variables" bo'limiga kiring:
   - `BOT_TOKEN` = tokeningiz
   - `ADMIN_ID` = telegram ID ingiz
5. Deploy tugmasini bosing ✅

---

## 👑 Admin buyruqlari
- Bot ishga tushganda `/start` bosing
- **Xodim qo'shish**: "➕ Xodim qo'shish" → xodim Telegram ID → ismi
- **Hisobot**: "📊 Umumiy hisobot" → davr tanlang
- **Masterlar**: "👥 Masterlar" → xodimni tanlang

## 👤 Xodim buyruqlari
- `/start` bosib kiriladi
- "🌅 Kunni boshlash" — ish boshlanadi
- Xizmat tugmasini bosganda narx kiritiladi
- "✅ Kunni yakunlash" — kun yakunlanadi

---

## 📋 Xizmatlar
- ✂️ Soch olish
- 🚿 Soch yuvish
- 🪒 Soqol olish
- 👰 Kiyov tayyorlash
- 💆 Yuz tozalash
- 🎭 Maska
- 🎨 Soch bo'yash

---

## 💰 Foiz tizimi
- 70% — xodim
- 30% — barbershop egasi (Behruz aka)
