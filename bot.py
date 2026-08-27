import asyncio
import aiosqlite
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# ---------- توکن و تنظیمات ----------
API_TOKEN = os.getenv("BOT_TOKEN", "8704302196:AAHSFYsMu11xwcwCtQ3TqcWC5fH7UC2WPto")
MASTER_ADMIN_ID = int(os.getenv("MASTER_ADMIN_ID", "7689823397"))

# برای Railway معمولاً نیازی به پروکسی نیست
# اگر نیاز دارید، می‌تونید از متغیر محیطی استفاده کنید
proxy_url = os.getenv("PROXY_URL", None)
if proxy_url:
    session = AiohttpSession(proxy=proxy_url)
    bot = Bot(token=API_TOKEN, session=session)
else:
    bot = Bot(token=API_TOKEN)

# ---------- ذخیره‌سازی state ----------
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ---------- مسیر دیتابیس ----------
DB_PATH = "shop.db"

# ---------- تعریف Stateها ----------
class AdminStates(StatesGroup):
    waiting_for_product_name = State()
    waiting_for_product_price = State()
    waiting_for_product_color = State()
    waiting_for_edit_id = State()
    waiting_for_edit_field = State()
    waiting_for_edit_value = State()
    waiting_for_delete_id = State()
    waiting_for_add_admin = State()
    waiting_for_remove_admin = State()

# ---------- مقداردهی اولیه دیتابیس ----------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price INTEGER NOT NULL,
                color TEXT
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cart (
                user_id INTEGER,
                product_id INTEGER,
                quantity INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, product_id),
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute(
            "INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)",
            (MASTER_ADMIN_ID, MASTER_ADMIN_ID)
        )
        
        await db.execute("DELETE FROM products")
        await db.commit()
        print("✅ دیتابیس مقداردهی اولیه شد.")

# ---------- تابع بررسی ادمین ----------
async def is_admin(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        return await cursor.fetchone() is not None

# ---------- تابع منوی اصلی ----------
async def send_menu(target, edit=False):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 مشاهده محصولات", callback_data="show_products")],
        [InlineKeyboardButton(text="🛒 مشاهده سبد خرید", callback_data="show_cart")],
        [InlineKeyboardButton(text="🧾 تسویه حساب", callback_data="checkout")]
    ])
    
    user_id = target.from_user.id if hasattr(target, 'from_user') else target.chat.id
    if await is_admin(user_id):
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔧 پنل ادمین", callback_data="admin_panel")])
    
    if edit:
        await target.edit_text("به فروشگاه خوش اومدی!", reply_markup=keyboard)
    else:
        await target.answer("به فروشگاه خوش اومدی!", reply_markup=keyboard)

# ---------- هندلر start ----------
@dp.message(Command("start"))
async def show_menu(message: types.Message):
    await send_menu(message)

# ---------- نمایش محصولات ----------
@dp.callback_query(lambda c: c.data == "show_products")
async def send_products(callback_query: types.CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id, name, price, color FROM products")
        rows = await cursor.fetchall()

    if not rows:
        await callback_query.message.edit_text("❌ متأسفانه هیچ محصولی موجود نیست.")
        await callback_query.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for pid, name, price, color in rows:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{name} - {price}$ ({color})",
                callback_data=f"buy_{pid}"
            )
        ])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_to_menu")])

    await callback_query.message.edit_text("📦 لیست محصولات:", reply_markup=keyboard)
    await callback_query.answer()

# ---------- افزودن به سبد خرید ----------
@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def buy_product(callback_query: types.CallbackQuery):
    pid = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT name FROM products WHERE id = ?", (pid,))
        product = await cursor.fetchone()
        if not product:
            await callback_query.answer("❌ محصول ناموجود!", show_alert=True)
            return
        await db.execute("""
            INSERT INTO cart (user_id, product_id, quantity)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, product_id) DO UPDATE SET quantity = quantity + 1
        """, (user_id, pid))
        await db.commit()
    await callback_query.answer(f"✅ {product[0]} به سبد خرید اضافه شد!")

# ---------- مشاهده سبد خرید ----------
@dp.callback_query(lambda c: c.data == "show_cart")
async def show_cart(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT p.id, p.name, p.price, c.quantity
            FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = ?
        """, (user_id,))
        items = await cursor.fetchall()
    if not items:
        await callback_query.message.edit_text("🛒 سبد خرید شما خالی است.")
        await callback_query.answer()
        return
    total = 0
    text = "🛒 سبد خرید شما:\n\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for pid, name, price, qty in items:
        total += price * qty
        text += f"• {name} × {qty} = {price * qty}$\n"
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=f"❌ کاهش یک {name}", callback_data=f"remove_{pid}")])
    text += f"\n💰 جمع کل: {total}$"
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_to_menu")])

    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()

# ---------- حذف از سبد خرید ----------
@dp.callback_query(lambda c: c.data.startswith("remove_"))
async def remove_from_cart(callback_query: types.CallbackQuery):
    pid = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT quantity FROM cart WHERE user_id = ? AND product_id = ?", (user_id, pid))
        row = await cursor.fetchone()
        if not row:
            await callback_query.answer("این محصول در سبد شما نیست!", show_alert=True)
            return
        if row[0] > 1:
            await db.execute("UPDATE cart SET quantity = quantity - 1 WHERE user_id = ? AND product_id = ?", (user_id, pid))
        else:
            await db.execute("DELETE FROM cart WHERE user_id = ? AND product_id = ?", (user_id, pid))
        await db.commit()
    await callback_query.answer("✅ تعداد کاهش یافت.")
    await show_cart(callback_query)

# ---------- تسویه حساب ----------
@dp.callback_query(lambda c: c.data == "checkout")
async def checkout(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT SUM(p.price * c.quantity)
            FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = ?
        """, (user_id,))
        total_row = await cursor.fetchone()
        total = total_row[0] if total_row[0] else 0

        if total == 0:
            await callback_query.answer("سبد خرید شما خالی است!", show_alert=True)
            return

        await db.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        await db.commit()

    await callback_query.answer()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_to_menu")]
    ])
    await callback_query.message.edit_text(f"✅ فاکتور شما به مبلغ {total}$ ثبت شد. سپاس!", reply_markup=keyboard)

# ---------- بازگشت به منو ----------
@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback_query: types.CallbackQuery):
    await send_menu(callback_query.message, edit=True)
    await callback_query.answer()

# ---------- پنل ادمین ----------
@dp.callback_query(lambda c: c.data == "admin_panel")
async def admin_panel(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی به پنل ادمین ندارید!", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن محصول", callback_data="admin_add_product")],
        [InlineKeyboardButton(text="✏️ ویرایش محصول", callback_data="admin_edit_product")],
        [InlineKeyboardButton(text="🗑 حذف محصول", callback_data="admin_delete_product")],
        [InlineKeyboardButton(text="👥 مدیریت ادمین‌ها", callback_data="admin_manage_admins")],
        [InlineKeyboardButton(text="📋 لیست ادمین‌ها", callback_data="admin_list_admins")],
        [InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_to_menu")]
    ])
    
    await callback_query.message.edit_text("🔧 پنل مدیریت فروشگاه:", reply_markup=keyboard)
    await callback_query.answer()

# ---------- مدیریت ادمین‌ها ----------
@dp.callback_query(lambda c: c.data == "admin_manage_admins")
async def manage_admins(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != MASTER_ADMIN_ID:
        await callback_query.answer("فقط ادمین اصلی می‌تونه ادمین مدیریت کنه!", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ اضافه کردن ادمین", callback_data="admin_add_admin")],
        [InlineKeyboardButton(text="❌ حذف ادمین", callback_data="admin_remove_admin")],
        [InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="admin_panel")]
    ])
    
    await callback_query.message.edit_text("👥 مدیریت ادمین‌ها:", reply_markup=keyboard)
    await callback_query.answer()

# ---------- اضافه کردن ادمین ----------
@dp.callback_query(lambda c: c.data == "admin_add_admin")
async def add_admin_start(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != MASTER_ADMIN_ID:
        await callback_query.answer("شما مجاز نیستید!", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_for_add_admin)
    await callback_query.message.edit_text("🔹 آی‌دی عددی کاربر مورد نظر را برای افزودن به ادمین‌ها وارد کنید:")
    await callback_query.answer()

@dp.message(AdminStates.waiting_for_add_admin)
async def add_admin_process(message: types.Message, state: FSMContext):
    if message.from_user.id != MASTER_ADMIN_ID:
        await message.answer("شما مجاز به این کار نیستید.")
        await state.clear()
        return
    
    try:
        user_id = int(message.text)
    except ValueError:
        await message.answer("❌ لطفاً یک آی‌دی عددی معتبر وارد کنید.")
        return
    
    if user_id == message.from_user.id:
        await message.answer("❌ شما خودتان از قبل ادمین هستید!")
        await state.clear()
        return
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        if await cursor.fetchone():
            await message.answer(f"❌ کاربر با آی‌دی {user_id} قبلاً ادمین است.")
            await state.clear()
            return
        
        await db.execute(
            "INSERT INTO admins (user_id, added_by) VALUES (?, ?)",
            (user_id, message.from_user.id)
        )
        await db.commit()
    
    await state.clear()
    await message.answer(f"✅ کاربر با آی‌دی {user_id} با موفقیت به لیست ادمین‌ها اضافه شد.")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="admin_panel")]
    ])
    await message.answer("🔧 به پنل ادمین بازگشتید.", reply_markup=keyboard)

# ---------- حذف ادمین ----------
@dp.callback_query(lambda c: c.data == "admin_remove_admin")
async def remove_admin_start(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != MASTER_ADMIN_ID:
        await callback_query.answer("شما مجاز نیستید!", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_for_remove_admin)
    await callback_query.message.edit_text("🔹 آی‌دی عددی کاربر مورد نظر برای حذف از ادمین‌ها را وارد کنید:")
    await callback_query.answer()

@dp.message(AdminStates.waiting_for_remove_admin)
async def remove_admin_process(message: types.Message, state: FSMContext):
    if message.from_user.id != MASTER_ADMIN_ID:
        await message.answer("شما مجاز به این کار نیستید.")
        await state.clear()
        return
    
    try:
        user_id = int(message.text)
    except ValueError:
        await message.answer("❌ لطفاً یک آی‌دی عددی معتبر وارد کنید.")
        return
    
    if user_id == MASTER_ADMIN_ID:
        await message.answer("❌ شما نمی‌توانید ادمین اصلی را حذف کنید!")
        await state.clear()
        return
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        if not await cursor.fetchone():
            await message.answer(f"❌ کاربر با آی‌دی {user_id} ادمین نیست.")
            await state.clear()
            return
        
        await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await db.commit()
    
    await state.clear()
    await message.answer(f"✅ کاربر با آی‌دی {user_id} از لیست ادمین‌ها حذف شد.")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="admin_panel")]
    ])
    await message.answer("🔧 به پنل ادمین بازگشتید.", reply_markup=keyboard)

# ---------- لیست ادمین‌ها ----------
@dp.callback_query(lambda c: c.data == "admin_list_admins")
async def list_admins(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT user_id, added_by, added_at 
            FROM admins 
            ORDER BY added_at
        """)
        rows = await cursor.fetchall()
    
    if not rows:
        await callback_query.message.edit_text("❌ هیچ ادمینی در سیستم ثبت نشده است.")
        await callback_query.answer()
        return
    
    text = "📋 لیست ادمین‌ها:\n\n"
    for idx, (user_id, added_by, added_at) in enumerate(rows, 1):
        text += f"{idx}. 🆔 {user_id}"
        if user_id == MASTER_ADMIN_ID:
            text += " 👑 (ادمین اصلی)"
        text += f"\n   ➕ افزوده شده توسط: {added_by}"
        text += f"\n   📅 تاریخ: {added_at}\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="admin_panel")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()

# ---------- دکمه‌های مدیریت محصولات ----------
@dp.callback_query(lambda c: c.data == "admin_add_product")
async def admin_add_product_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_for_product_name)
    await callback_query.message.edit_text("نام محصول را وارد کنید:")
    await callback_query.answer()

@dp.message(AdminStates.waiting_for_product_name)
async def add_product_name(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("شما دسترسی ندارید!")
        await state.clear()
        return
    await state.update_data(name=message.text)
    await state.set_state(AdminStates.waiting_for_product_price)
    await message.answer("قیمت (به دلار) را وارد کنید:")

@dp.message(AdminStates.waiting_for_product_price)
async def add_product_price(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("شما دسترسی ندارید!")
        await state.clear()
        return
    try:
        price = int(message.text)
    except ValueError:
        await message.answer("لطفاً یک عدد وارد کنید.")
        return
    await state.update_data(price=price)
    await state.set_state(AdminStates.waiting_for_product_color)
    await message.answer("رنگ محصول را وارد کنید:")

@dp.message(AdminStates.waiting_for_product_color)
async def add_product_color(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("شما دسترسی ندارید!")
        await state.clear()
        return
    data = await state.get_data()
    name = data['name']
    price = data['price']
    color = message.text

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT MAX(id) FROM products")
        last_id = await cursor.fetchone()
        new_id = (last_id[0] or 0) + 1
        await db.execute("INSERT INTO products (id, name, price, color) VALUES (?, ?, ?, ?)",
                        (new_id, name, price, color))
        await db.commit()

    await state.clear()
    await message.answer(f"✅ محصول '{name}' با موفقیت اضافه شد (ID: {new_id}).")

# ---------- ویرایش محصول ----------
@dp.callback_query(lambda c: c.data == "admin_edit_product")
async def edit_product_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_for_edit_id)
    await callback_query.message.edit_text("آی‌دی محصول مورد نظر برای ویرایش را وارد کنید:")
    await callback_query.answer()

@dp.message(AdminStates.waiting_for_edit_id)
async def edit_product_id(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("شما دسترسی ندارید!")
        await state.clear()
        return
    try:
        pid = int(message.text)
    except ValueError:
        await message.answer("لطفاً یک عدد معتبر وارد کنید.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT name FROM products WHERE id = ?", (pid,))
        row = await cursor.fetchone()
    if not row:
        await message.answer("محصولی با این آی‌دی وجود ندارد.")
        await state.clear()
        return
    await state.update_data(edit_id=pid)
    await state.set_state(AdminStates.waiting_for_edit_field)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="نام", callback_data="edit_field_name")],
        [InlineKeyboardButton(text="قیمت", callback_data="edit_field_price")],
        [InlineKeyboardButton(text="رنگ", callback_data="edit_field_color")]
    ])
    await message.answer("کدام فیلد را می‌خواهید ویرایش کنید؟", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith("edit_field_"))
async def edit_field_selection(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    field = callback_query.data.split("_")[2]
    await state.update_data(edit_field=field)
    await state.set_state(AdminStates.waiting_for_edit_value)
    await callback_query.message.edit_text(f"مقدار جدید برای '{field}' را وارد کنید:")
    await callback_query.answer()

@dp.message(AdminStates.waiting_for_edit_value)
async def edit_product_value(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("شما دسترسی ندارید!")
        await state.clear()
        return
    data = await state.get_data()
    pid = data['edit_id']
    field = data['edit_field']
    value = message.text

    if field == 'price':
        try:
            value = int(value)
        except ValueError:
            await message.answer("لطفاً یک عدد معتبر وارد کنید.")
            return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE products SET {field} = ? WHERE id = ?", (value, pid))
        await db.commit()

    await state.clear()
    await message.answer(f"✅ فیلد '{field}' با موفقیت به '{value}' تغییر یافت.")

# ---------- حذف محصول ----------
@dp.callback_query(lambda c: c.data == "admin_delete_product")
async def delete_product_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_for_delete_id)
    await callback_query.message.edit_text("آی‌دی محصول مورد نظر برای حذف را وارد کنید:")
    await callback_query.answer()

@dp.message(AdminStates.waiting_for_delete_id)
async def delete_product_process(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("شما دسترسی ندارید!")
        await state.clear()
        return
    try:
        pid = int(message.text)
    except ValueError:
        await message.answer("لطفاً یک عدد معتبر وارد کنید.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT name FROM products WHERE id = ?", (pid,))
        row = await cursor.fetchone()
        if not row:
            await message.answer("محصولی با این آی‌دی وجود ندارد.")
            await state.clear()
            return
        await db.execute("DELETE FROM products WHERE id = ?", (pid,))
        await db.commit()
    await state.clear()
    await message.answer(f"✅ محصول '{row[0]}' با آی‌دی {pid} حذف شد.")

# ---------- اجرای اصلی ----------
async def main():
    print("ربات در حال راه‌اندازی...")
    await init_db()
    print("ربات روشن شد...")

    while True:
        try:
            await dp.start_polling(bot)
        except Exception as e:
            print(f"خطا رخ داد: {e}")
            print("تلاش مجدد در 5 ثانیه...")
            await asyncio.sleep(5)
            continue

if __name__ == "__main__":
    asyncio.run(main())