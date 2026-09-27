
import os
import sqlite3
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "8628267774"))
ENTRY_FEE = 30
QR_PATH = os.path.join(os.path.dirname(__file__), "payment_qr.png")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Put your BotFather token in .env")

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

conn = sqlite3.connect("fxbr.db")
conn.execute("""
CREATE TABLE IF NOT EXISTS registrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER,
    username TEXT,
    name TEXT,
    uid TEXT,
    ign TEXT,
    status TEXT DEFAULT 'pending',
    slot INTEGER,
    screenshot_file_id TEXT
)
""")
conn.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")
conn.commit()

class Reg(StatesGroup):
    name = State()
    uid = State()
    ign = State()
    payment = State()

def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Register", callback_data="register")],
        [InlineKeyboardButton(text="🎟️ My Registration", callback_data="myreg")],
        [InlineKeyboardButton(text="🔐 Room ID & Password", callback_data="room")],
        [InlineKeyboardButton(text="📜 Rules", callback_data="rules")],
        [InlineKeyboardButton(text="🏆 Results", callback_data="results")]
    ])

def admin_kb(reg_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Approve", callback_data=f"approve:{reg_id}")],
        [InlineKeyboardButton(text="❌ Reject", callback_data=f"reject:{reg_id}")]
    ])

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "🎮 <b>FX BR SOLO TOURNAMENT</b>\n\n"
        "💰 Entry Fee: <b>₹30</b>\n"
        "👤 Mode: <b>Solo</b>\n\n"
        "Register করে payment screenshot পাঠাও।\n"
        "Admin approve করার পর slot number পাওয়া যাবে।",
        reply_markup=main_kb(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "register")
async def register(call: CallbackQuery, state: FSMContext):
    cur = conn.execute(
        "SELECT id FROM registrations WHERE telegram_id=? AND status IN ('pending','approved')",
        (call.from_user.id,)
    )
    if cur.fetchone():
        await call.answer("তোমার registration already আছে।", show_alert=True)
        return
    await state.set_state(Reg.name)
    await call.message.answer("👤 তোমার নাম লিখো:")
    await call.answer()

@dp.message(Reg.name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(Reg.uid)
    await message.answer("🆔 Free Fire UID লিখো:")

@dp.message(Reg.uid)
async def reg_uid(message: Message, state: FSMContext):
    await state.update_data(uid=message.text.strip())
    await state.set_state(Reg.ign)
    await message.answer("🎮 In-game Name (IGN) লিখো:")

@dp.message(Reg.ign)
async def reg_ign(message: Message, state: FSMContext):
    await state.update_data(ign=message.text.strip())
    await state.set_state(Reg.payment)
    if os.path.exists(QR_PATH):
        await message.answer_photo(
            FSInputFile(QR_PATH),
            caption="💰 Entry Fee: ₹30\n\nএই QR-এ payment করে তারপর <b>Payment Screenshot</b> এখানে পাঠাও।",
            parse_mode="HTML"
        )
    else:
        await message.answer("💰 Entry Fee: ₹30\nPayment করে screenshot পাঠাও।")

@dp.message(Reg.payment, F.photo)
async def reg_payment(message: Message, state: FSMContext):
    data = await state.get_data()
    file_id = message.photo[-1].file_id
    cur = conn.execute(
        "INSERT INTO registrations (telegram_id,username,name,uid,ign,screenshot_file_id) VALUES (?,?,?,?,?,?)",
        (message.from_user.id, message.from_user.username or "", data["name"], data["uid"], data["ign"], file_id)
    )
    reg_id = cur.lastrowid
    conn.commit()
    await state.clear()

    await message.answer(
        "✅ Payment screenshot received!\n"
        "⏳ Admin verification চলছে। Approve হলে slot number দেওয়া হবে।",
        reply_markup=main_kb()
    )

    admin_text = (
        f"🆕 <b>NEW REGISTRATION #{reg_id}</b>\n\n"
        f"👤 Name: {data['name']}\n"
        f"🎮 IGN: {data['ign']}\n"
        f"🆔 UID: {data['uid']}\n"
        f"📱 Username: @{message.from_user.username or 'N/A'}\n"
        f"💰 Fee: ₹30"
    )
    await bot.send_photo(
        ADMIN_ID,
        file_id,
        caption=admin_text,
        parse_mode="HTML",
        reply_markup=admin_kb(reg_id)
    )

@dp.message(Reg.payment)
async def payment_wrong(message: Message):
    await message.answer("📷 দয়া করে payment-এর screenshot/photo পাঠাও।")

@dp.callback_query(F.data.startswith("approve:"))
async def approve(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Admin only.", show_alert=True)
        return
    reg_id = int(call.data.split(":")[1])
    cur = conn.execute("SELECT telegram_id FROM registrations WHERE id=? AND status='pending'", (reg_id,))
    row = cur.fetchone()
    if not row:
        await call.answer("Registration পাওয়া যায়নি/আগেই processed.", show_alert=True)
        return
    cur = conn.execute("SELECT COALESCE(MAX(slot),0)+1 FROM registrations WHERE status='approved'")
    slot = cur.fetchone()[0]
    conn.execute("UPDATE registrations SET status='approved',slot=? WHERE id=?", (slot, reg_id))
    conn.commit()
    await bot.send_message(
        row[0],
        f"🎉 <b>Payment Approved!</b>\n\n🎟️ Your Slot: <b>{slot}</b>\n\n"
        "Match-এর সময় Room ID & Password এই bot থেকেই দেখতে পারবে।",
        parse_mode="HTML",
        reply_markup=main_kb()
    )
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("Approved ✅")

@dp.callback_query(F.data.startswith("reject:"))
async def reject(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Admin only.", show_alert=True)
        return
    reg_id = int(call.data.split(":")[1])
    cur = conn.execute("SELECT telegram_id FROM registrations WHERE id=?", (reg_id,))
    row = cur.fetchone()
    if not row:
        await call.answer("Registration পাওয়া যায়নি.", show_alert=True)
        return
    conn.execute("UPDATE registrations SET status='rejected' WHERE id=?", (reg_id,))
    conn.commit()
    await bot.send_message(row[0], "❌ তোমার payment/registration reject করা হয়েছে। Admin-এর সাথে যোগাযোগ করো।")
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("Rejected ❌")

@dp.callback_query(F.data == "myreg")
async def myreg(call: CallbackQuery):
    cur = conn.execute(
        "SELECT name,uid,ign,status,slot FROM registrations WHERE telegram_id=? ORDER BY id DESC LIMIT 1",
        (call.from_user.id,)
    )
    r = cur.fetchone()
    if not r:
        await call.message.answer("তোমার কোনো registration নেই।", reply_markup=main_kb())
    else:
        await call.message.answer(
            f"👤 Name: {r[0]}\n🎮 IGN: {r[2]}\n🆔 UID: {r[1]}\n"
            f"📌 Status: {r[3]}\n🎟️ Slot: {r[4] or 'Not assigned'}",
            reply_markup=main_kb()
        )
    await call.answer()

@dp.callback_query(F.data == "room")
async def room(call: CallbackQuery):
    cur = conn.execute("SELECT status FROM registrations WHERE telegram_id=? ORDER BY id DESC LIMIT 1", (call.from_user.id,))
    r = cur.fetchone()
    if not r or r[0] != "approved":
        await call.message.answer("🔒 আগে registration/payment approve হতে হবে।")
        await call.answer()
        return
    room_id = conn.execute("SELECT value FROM settings WHERE key='room_id'").fetchone()
    password = conn.execute("SELECT value FROM settings WHERE key='room_password'").fetchone()
    if not room_id or not password:
        await call.message.answer("⏳ Room ID & Password এখনো দেওয়া হয়নি।")
    else:
        await call.message.answer(f"🔐 <b>Room ID:</b> {room_id[0]}\n🔑 <b>Password:</b> {password[0]}", parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "rules")
async def rules(call: CallbackQuery):
    await call.message.answer(
        "📜 <b>FX BR SOLO RULES</b>\n\n"
        "1. No team up — team up করলে no prize/no refund.\n"
        "2. No revive.\n"
        "3. E-sports mode ON.\n"
        "4. Random kill করলে no prize.\n"
        "5. যে slot number পাবে, সেই slot-এ থাকতে হবে; না হলে kick/no refund.\n"
        "6. All gun & all character skills allowed.\n"
        "7. Network/other personal issues-এর জন্য management দায়ী নয়.",
        parse_mode="HTML"
    )
    await call.answer()

@dp.callback_query(F.data == "results")
async def results(call: CallbackQuery):
    text = conn.execute("SELECT value FROM settings WHERE key='results'").fetchone()
    await call.message.answer(text[0] if text else "🏆 Results এখনো publish করা হয়নি।")
    await call.answer()

@dp.message(F.text.startswith("/setroom "))
async def setroom(message: Message):
    if message.from_user.id != ADMIN_ID: return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Use: /setroom ROOM_ID PASSWORD")
        return
    room_id, password = parts[1], parts[2]
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('room_id',?)", (room_id,))
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('room_password',?)", (password,))
    conn.commit()
    await message.answer("🔐 Room ID & Password saved.")

@dp.message(F.text.startswith("/setresults "))
async def setresults(message: Message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text[len("/setresults "):].strip()
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('results',?)", (text,))
    conn.commit()
    await message.answer("🏆 Results updated.")

@dp.message(F.text == "/admin")
async def admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    count = conn.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]
    approved = conn.execute("SELECT COUNT(*) FROM registrations WHERE status='approved'").fetchone()[0]
    await message.answer(
        f"👑 <b>FX BR ADMIN</b>\n\n"
        f"Total registrations: {count}\nApproved: {approved}\n\n"
        "🔐 Room set: /setroom ROOM_ID PASSWORD\n"
        "🏆 Results: /setresults YOUR_RESULT",
        parse_mode="HTML"
    )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
