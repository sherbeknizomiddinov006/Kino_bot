import asyncio
import logging
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import asyncpg

# ===================== SOZLAMALAR =====================
TOKEN = "8352093089:AAFlkn4pcsuYvSAzXcrgpmCIQeUfxq54gE0"
ADMIN_ID = 8320643359
DATABASE_URL = "postgresql://postgres:TcFdaaGuouwLnwneUoemLtSnTaQWZvMa@reseau.proxy.rlwy.net:57864/railway"

logging.basicConfig(level=logging.DEBUG)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

class SearchState(StatesGroup):
    waiting_for_code = State()

# ===================== MENYU =====================
def get_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Kino qidirish")],
            [KeyboardButton(text="📺 Bizning Kanal")],
            [KeyboardButton(text="📢 Kanal Admini")],
            [KeyboardButton(text="🤖 Bot Yaratish bo'yicha Admin")]
        ],
        resize_keyboard=True
    )

# ===================== MENYU HANDLERLARI =====================
@dp.message(F.text == "🔍 Kino qidirish")
async def ask_code(message: types.Message, state: FSMContext):
    await state.set_state(SearchState.waiting_for_code)
    await message.answer("🔢 Kino kodini yuboring:")

@dp.message(F.text == "📺 Bizning Kanal")
async def our_channel(message: types.Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📺 Fantastik Kino Kanaliga O'tish", url="https://t.me/fantastikkinos")]
        ]
    )
    await message.answer(
        "🎬 <b>Bizning Rasmiy Kanal</b>\n\n"
        "Barcha yangi kinolar shu yerdan chiqadi 👇",
        reply_markup=keyboard
    )

@dp.message(F.text == "📢 Kanal Admini")
async def channel_admin(message: types.Message):
    await message.answer(
        "📢 <b>Kanal bo'yicha savollaringiz bo'lsa:</b>\n\n"
        "👤 @ogabek_temirov"
    )

@dp.message(F.text == "🤖 Bot Yaratish bo'yicha Admin")
async def bot_admin(message: types.Message):
    await message.answer(
        "🤖 <b>Bot yaratish bo'yicha zakazlar uchun:</b>\n\n"
        "👨‍💻 @nizomiddinov_0414"
    )

# ===================== DATABASE =====================
async def get_db_pool():
    try:
        pool = await asyncpg.create_pool(DATABASE_URL)
        print("✅ PostgreSQL ga muvaffaqiyatli ulandi!")
        return pool
    except Exception as e:
        print(f"❌ DB ulanish xatosi: {e}")
        raise

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS movies (
                id SERIAL PRIMARY KEY,
                code TEXT NOT NULL,
                file_id TEXT NOT NULL,
                file_unique_id TEXT NOT NULL,
                caption TEXT,
                duration INTEGER DEFAULT 0,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code, file_unique_id)
            )
        ''')
        await conn.execute('''
            ALTER TABLE movies
            ADD COLUMN IF NOT EXISTS duration INTEGER DEFAULT 0;
        ''')
        print("✅ Jadval muvaffaqiyatli yangilandi!")

async def add_movie(pool, code, file_id, file_unique_id, caption, duration=0):
    async with pool.acquire() as conn:
        try:
            await conn.execute('''
                INSERT INTO movies (code, file_id, file_unique_id, caption, duration)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (code, file_unique_id) DO NOTHING
            ''', code, file_id, file_unique_id, caption, duration)
            return True
        except Exception as e:
            print(f"Saqlash xatosi: {e}")
            return False

async def get_movies(pool, code):
    async with pool.acquire() as conn:
        return await conn.fetch('SELECT file_id, caption, duration FROM movies WHERE code = $1', code)

# ===================== MIDDLEWARE =====================
class DatabaseMiddleware:
    def __init__(self, pool):
        self.pool = pool
    async def __call__(self, handler, event, data):
        data["pool"] = self.pool
        return await handler(event, data)

# ===================== ASOSIY HANDLERLAR =====================
@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext, pool):
    await state.clear()
    await message.answer(f"Salom {message.from_user.full_name}!", reply_markup=get_main_menu())

@dp.message(SearchState.waiting_for_code, F.text)
async def search(message: types.Message, state: FSMContext, pool):
    match = re.search(r'\d+', message.text)
    if not match:
        await message.answer("Kod faqat raqamlardan iborat bo'ladi.")
        return
    code = match.group()
    results = await get_movies(pool, code)
    if results:
        for record in results:
            try:
                await message.answer_video(video=record['file_id'], caption=record.get('caption', ''))
            except:
                await message.answer_document(document=record['file_id'], caption=record.get('caption', ''))
        await state.clear()
        await message.answer("✅ Topildi!", reply_markup=get_main_menu())
    else:
        await message.answer(f"😔 {code} topilmadi.")

# ===================== KANAL VA FORWARD SAQLASH =====================
MIN_DURATION = 1500

@dp.channel_post(F.video | F.document)
async def save_from_channel(message: types.Message, pool):
    text = message.caption or ""
    match = re.search(r'(\d+)', text)
    if not match:
        return
    code = match.group(1)
    media = message.video or message.document
    if not media:
        return
    duration = getattr(media, 'duration', 0)
   
    if duration < MIN_DURATION:
        await message.reply(f"⚠️ #{code} — qisqa video ({duration//60} daqiqa). 30 daqiqadan uzunroq yuboring.")
        return
   
    success = await add_movie(pool, code, media.file_id, media.file_unique_id, text, duration)
    if success:
        await message.reply(f"✅ Kanaldan saqlandi: #{code} ({duration//60} daqiqa)")
    else:
        await message.reply(f"ℹ️ #{code} allaqachon bor.")

@dp.message(F.forward_from_chat)
async def save_forwarded_movie(message: types.Message, pool):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.caption or ""
    match = re.search(r'(\d+)', text)
    if not match:
        await message.answer("❌ Captionda kod topilmadi.")
        return
    code = match.group(1)
    media = message.video or message.document
    if not media:
        await message.answer("❌ Video topilmadi.")
        return
    duration = getattr(media, 'duration', 0)
   
    if duration < MIN_DURATION:
        await message.answer(f"⚠️ #{code} — qisqa video ({duration//60} daqiqa). Faqat 30+ daqiqalik to‘liq kinoni yuboring.")
        return
   
    success = await add_movie(pool, code, media.file_id, media.file_unique_id, text, duration)
   
    if success:
        await message.answer(f"✅ Forward saqlandi: #{code} ({duration//60} daqiqa)")
    else:
        await message.answer(f"ℹ️ #{code} allaqachon bor.")

# ===================== ADMIN =====================
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🛠 /del KOD — o‘chirish\n/all — barcha kodlar")

@dp.message(Command("del"))
async def delete_movie(message: types.Message, pool):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        code = message.text.split()[1]
    except:
        await message.answer("Foydalanish: /del KOD")
        return
    async with pool.acquire() as conn:
        res = await conn.execute('DELETE FROM movies WHERE code = $1', code)
    await message.answer(f"✅ #{code} o‘chirildi!")

@dp.message(Command("clearall"))
async def clear_all_movies(message: types.Message, pool):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Ruxsat yo‘q!")
        return
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM movies")
        await conn.execute("ALTER SEQUENCE movies_id_seq RESTART WITH 1")
    await message.answer("🗑️ **Barcha kinolar bazadan o‘chirildi!**")
    print("🗑️ Baza tozalandi!")

# ===================== MAIN =====================
async def main():
    pool = await get_db_pool()
    await init_db(pool)
   
    dp.message.middleware(DatabaseMiddleware(pool))
    dp.channel_post.middleware(DatabaseMiddleware(pool))
   
    print("🚀 Bot muvaffaqiyatli ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())