import asyncio
import aiosqlite
import os
import uuid
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from datetime import datetime
import zarinpal

# ---------- توکن و تنظیمات ----------
API_TOKEN = os.getenv("BOT_TOKEN", "8704302196:AAHSFYsMu11xwcwCtQ3TqcWC5fH7UC2WPto")
MASTER_ADMIN_ID = int(os.getenv("MASTER_ADMIN_ID", "7689823397"))

# تنظیمات زرین‌پال
ZARINPAL_MERCHANT_ID = os.getenv("ZARINPAL_MERCHANT_ID", "YOUR_MERCHANT_ID")
ZARINPAL_CALLBACK_URL = os.getenv("ZARINPAL_CALLBACK_URL", "https://your-railway-app.railway.app/callback")

proxy_url = os.getenv("PROXY_URL", None)
if proxy_url:
    session = AiohttpSession(proxy=proxy_url)
    bot = Bot(token=API_TOKEN, session=session)
else:
    bot = Bot(token=API_TOKEN)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

DB_PATH = "shop.db"

# ---------- تعریف Stateها ----------
class AdminStates(StatesGroup):
    waiting_for_category_name = State()
    waiting_for_category_parent = State()
    waiting_for_product_name = State()
    waiting_for_product_price = State()
    waiting_for_product_category = State()
    waiting_for_product_description = State()
    waiting_for_edit_id = State()
    waiting_for_edit_field = State()
    waiting_for_edit_value = State()
    waiting_for_delete_id = State()
    waiting_for_add_admin = State()
    waiting_for_remove_admin = State()
    waiting_for_order_status = State()

# ---------- مقداردهی اولیه دیتابیس ----------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # جدول دسته‌بندی (سلسله‌مراتبی)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_id INTEGER,
                FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE CASCADE
            )
        """)

        # جدول محصولات با دسته‌بندی
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price INTEGER NOT NULL,
                description TEXT,
                category_id INTEGER,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
            )
        """)

        # جدول سبد خرید
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cart (
                user_id INTEGER,
                product_id INTEGER,
                quantity INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, product_id),
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        """)

        # جدول ادمین‌ها
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # جدول سفارشات
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                items TEXT,
                total_price INTEGER,
                status TEXT DEFAULT 'pending',
                tracking_code TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # جدول پرداخت‌ها
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id TEXT PRIMARY KEY,
                order_id TEXT,
                user_id INTEGER,
                amount INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(id)
            )
        """)

        # اضافه کردن ادمین اصلی
        await db.execute(
            "INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)",
            (MASTER_ADMIN_ID, MASTER_ADMIN_ID)
        )

        # ایجاد دسته‌بندی نمونه
        cursor = await db.execute("SELECT COUNT(*) FROM categories")
        count = await cursor.fetchone()
        if count[0] == 0:
            # دسته‌بندی اصلی
            await db.execute("INSERT INTO categories (name, parent_id) VALUES (?, NULL)", ("الکترونیک",))
            await db.execute("INSERT INTO categories (name, parent_id) VALUES (?, NULL)", ("پوشاک",))
            await db.execute("INSERT INTO categories (name, parent_id) VALUES (?, NULL)", ("کتاب",))
            
            # زیردسته‌ها
            cursor = await db.execute("SELECT id FROM categories WHERE name = 'الکترونیک'")
            electronic_id = (await cursor.fetchone())[0]
            await db.execute("INSERT INTO categories (name, parent_id) VALUES (?, ?)", ("گوشی موبایل", electronic_id))
            await db.execute("INSERT INTO categories (name, parent_id) VALUES (?, ?)", ("لپ‌تاپ", electronic_id))
            
            cursor = await db.execute("SELECT id FROM categories WHERE name = 'پوشاک'")
            clothing_id = (await cursor.fetchone())[0]
            await db.execute("INSERT INTO categories (name, parent_id) VALUES (?, ?)", ("مردانه", clothing_id))
            await db.execute("INSERT INTO categories (name, parent_id) VALUES (?, ?)", ("زنانه", clothing_id))
            
            # محصولات نمونه
            cursor = await db.execute("SELECT id FROM categories WHERE name = 'گوشی موبایل'")
            phone_category_id = (await cursor.fetchone())[0]
            await db.execute(
                "INSERT INTO products (name, price, description, category_id) VALUES (?, ?, ?, ?)",
                ("سامسونگ گلکسی S24", 50000000, "گوشی هوشمند با دوربین قدرتمند", phone_category_id)
            )
            await db.execute(
                "INSERT INTO products (name, price, description, category_id) VALUES (?, ?, ?, ?)",
                ("آیفون 15 پرو", 80000000, "گوشی پرچمدار اپل", phone_category_id)
            )
            
            cursor = await db.execute("SELECT id FROM categories WHERE name = 'لپ‌تاپ'")
            laptop_category_id = (await cursor.fetchone())[0]
            await db.execute(
                "INSERT INTO products (name, price, description, category_id) VALUES (?, ?, ?, ?)",
                ("ایسوس ROG", 120000000, "لپ‌تاپ گیمینگ قدرتمند", laptop_category_id)
            )
            
            await db.commit()
            print("✅ دسته‌بندی و محصولات نمونه اضافه شدند.")

        await db.commit()
        print("✅ دیتابیس مقداردهی اولیه شد.")

# ---------- توابع کمکی ----------
async def health_check(request):
    return web.Response(text="OK", status=200)

async def payment_callback(request):
    """پردازش بازگشت از درگاه پرداخت"""
    try:
        data = await request.post()
        authority = data.get('Authority')
        status = data.get('Status')
        
        if status != 'OK':
            return web.Response(text="پرداخت ناموفق بود", status=400)
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT amount, user_id, order_id FROM payments WHERE id = ? AND status = 'pending'",
                (authority,)
            )
            payment = await cursor.fetchone()
            
            if not payment:
                return web.Response(text="پرداخت یافت نشد", status=404)
            
            amount, user_id, order_id = payment
            
            zarinpal_client = zarinpal.ZarinPal(merchant_id=ZARINPAL_MERCHANT_ID)
            result = zarinpal_client.verify(
                authority=authority,
                amount=amount
            )
            
            if result.is_paid:
                # بروزرسانی وضعیت پرداخت
                await db.execute(
                    "UPDATE payments SET status = 'paid', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (authority,)
                )
                
                # بروزرسانی وضعیت سفارش
                await db.execute(
                    "UPDATE orders SET status = 'processing', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (order_id,)
                )
                
                # دریافت اطلاعات سفارش
                cursor = await db.execute(
                    "SELECT items, total_price FROM orders WHERE id = ?",
                    (order_id,)
                )
                order_data = await cursor.fetchone()
                items, total_price = order_data
                
                # حذف از سبد خرید
                await db.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
                await db.commit()
                
                # ارسال پیام تایید به کاربر
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📦 پیگیری سفارش", callback_data=f"track_order_{order_id}")],
                    [InlineKeyboardButton(text="🏠 بازگشت به منو", callback_data="back_to_menu")]
                ])
                
                await bot.send_message(
                    user_id,
                    f"✅ پرداخت شما به مبلغ {total_price:,} تومان با موفقیت انجام شد!\n"
                    f"📋 شماره سفارش: {order_id[:8].upper()}\n"
                    "از خرید شما متشکریم 🙏",
                    reply_markup=keyboard
                )
                
                # ارسال سفارش به همه ادمین‌ها
                await notify_admins(order_id, user_id, items, total_price)
                
                return web.Response(text="پرداخت با موفقیت انجام شد", status=200)
            else:
                await db.execute(
                    "UPDATE payments SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (authority,)
                )
                await db.execute(
                    "UPDATE orders SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (order_id,)
                )
                await db.commit()
                
                await bot.send_message(
                    user_id,
                    "❌ پرداخت شما ناموفق بود. لطفاً دوباره تلاش کنید."
                )
                
                return web.Response(text="پرداخت ناموفق", status=400)
                
    except Exception as e:
        print(f"خطا در callback پرداخت: {e}")
        return web.Response(text="خطا در پردازش پرداخت", status=500)

async def notify_admins(order_id, user_id, items, total_price):
    """ارسال سفارش به همه ادمین‌ها"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM admins")
        admins = await cursor.fetchall()
    
    items_list = json.loads(items)
    items_text = "\n".join([f"• {item['name']} × {item['quantity']} = {item['price']:,} تومان" for item in items_list])
    
    for admin_id in admins:
        try:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ تایید سفارش", callback_data=f"approve_order_{order_id}")],
                [InlineKeyboardButton(text="❌ لغو سفارش", callback_data=f"reject_order_{order_id}")],
                [InlineKeyboardButton(text="📦 تغییر وضعیت", callback_data=f"change_status_{order_id}")]
            ])
            
            await bot.send_message(
                admin_id[0],
                f"🆕 سفارش جدید!\n\n"
                f"📋 شماره سفارش: {order_id[:8].upper()}\n"
                f"👤 کاربر: {user_id}\n"
                f"📦 اقلام سفارش:\n{items_text}\n"
                f"💰 مبلغ کل: {total_price:,} تومان\n"
                f"📅 تاریخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"خطا در ارسال به ادمین {admin_id[0]}: {e}")

async def start_health_server():
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/', health_check)
    app.router.add_post('/callback', payment_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=8080)
    await site.start()
    print("✅ Healthcheck server started on port 8080")

async def is_admin(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        return await cursor.fetchone() is not None

async def get_category_tree(parent_id=None, level=0):
    """دریافت درخت دسته‌بندی"""
    async with aiosqlite.connect(DB_PATH) as db:
        if parent_id is None:
            cursor = await db.execute("SELECT id, name FROM categories WHERE parent_id IS NULL")
        else:
            cursor = await db.execute("SELECT id, name FROM categories WHERE parent_id = ?", (parent_id,))
        categories = await cursor.fetchall()
        
        result = []
        for cat_id, name in categories:
            result.append((cat_id, name, level))
            # دریافت زیردسته‌ها به صورت بازگشتی
            sub_categories = await get_category_tree(cat_id, level + 1)
            result.extend(sub_categories)
        return result

# ---------- منوی اصلی ----------
async def send_menu(target, edit=False):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 مشاهده محصولات", callback_data="show_categories")],
        [InlineKeyboardButton(text="🛒 مشاهده سبد خرید", callback_data="show_cart")],
        [InlineKeyboardButton(text="📦 پیگیری سفارش", callback_data="track_order_menu")],
        [InlineKeyboardButton(text="🧾 تسویه حساب", callback_data="checkout")]
    ])

    user_id = target.from_user.id if hasattr(target, 'from_user') else target.chat.id
    if await is_admin(user_id):
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔧 پنل ادمین", callback_data="admin_panel")])

    if edit:
        await target.edit_text("🛍 به فروشگاه خوش اومدی!", reply_markup=keyboard)
    else:
        await target.answer("🛍 به فروشگاه خوش اومدی!", reply_markup=keyboard)

# ---------- نمایش دسته‌بندی ----------
@dp.callback_query(lambda c: c.data == "show_categories")
async def show_categories(callback_query: types.CallbackQuery):
    categories = await get_category_tree()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for cat_id, name, level in categories:
        indent = "  " * level
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"{indent}📁 {name}", callback_data=f"cat_{cat_id}")
        ])
    
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_to_menu")])
    
    await callback_query.message.edit_text("📂 دسته‌بندی محصولات:", reply_markup=keyboard)
    await callback_query.answer()

# ---------- نمایش محصولات یک دسته ----------
@dp.callback_query(lambda c: c.data.startswith("cat_"))
async def show_category_products(callback_query: types.CallbackQuery):
    cat_id = int(callback_query.data.split("_")[1])
    
    async with aiosqlite.connect(DB_PATH) as db:
        # بررسی محصولات این دسته
        cursor = await db.execute(
            "SELECT id, name, price, description FROM products WHERE category_id = ?",
            (cat_id,)
        )
        products = await cursor.fetchall()
        
        # بررسی زیردسته‌ها
        cursor = await db.execute("SELECT id, name FROM categories WHERE parent_id = ?", (cat_id,))
        sub_categories = await cursor.fetchall()
    
    if not products and not sub_categories:
        await callback_query.answer("این دسته خالی است!", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    # نمایش زیردسته‌ها
    for sub_id, name in sub_categories:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"📁 {name}", callback_data=f"cat_{sub_id}")
        ])
    
    # نمایش محصولات
    for pid, name, price, description in products:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"🛍 {name} - {price:,} تومان",
                callback_data=f"product_{pid}"
            )
        ])
    
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 بازگشت به دسته‌بندی", callback_data="show_categories")])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_to_menu")])
    
    await callback_query.message.edit_text("📦 محصولات این دسته:", reply_markup=keyboard)
    await callback_query.answer()

# ---------- مشاهده جزئیات محصول ----------
@dp.callback_query(lambda c: c.data.startswith("product_"))
async def show_product_detail(callback_query: types.CallbackQuery):
    pid = int(callback_query.data.split("_")[1])
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT name, price, description FROM products WHERE id = ?",
            (pid,)
        )
        product = await cursor.fetchone()
        
        if not product:
            await callback_query.answer("محصول یافت نشد!", show_alert=True)
            return
        
        name, price, description = product
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 افزودن به سبد خرید", callback_data=f"buy_{pid}")],
            [InlineKeyboardButton(text="🔙 بازگشت به دسته", callback_data=f"cat_back_{pid}")]
        ])
        
        await callback_query.message.edit_text(
            f"📦 {name}\n\n"
            f"💰 قیمت: {price:,} تومان\n"
            f"📝 توضیحات: {description or 'بدون توضیحات'}\n\n"
            f"برای خرید روی دکمه زیر کلیک کنید.",
            reply_markup=keyboard
        )
        await callback_query.answer()

# ---------- بازگشت به دسته از محصول ----------
@dp.callback_query(lambda c: c.data.startswith("cat_back_"))
async def back_to_category_from_product(callback_query: types.CallbackQuery):
    pid = int(callback_query.data.split("_")[2])
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT category_id FROM products WHERE id = ?", (pid,))
        result = await cursor.fetchone()
        if result:
            cat_id = result[0]
            # شبیه‌سازی callback cat_
            callback_query.data = f"cat_{cat_id}"
            await show_category_products(callback_query)

# ---------- افزودن به سبد خرید ----------
@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def buy_product(callback_query: types.CallbackQuery):
    pid = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT name, price FROM products WHERE id = ?", (pid,))
        product = await cursor.fetchone()
        if not product:
            await callback_query.answer("❌ محصول ناموجود!", show_alert=True)
            return
        
        name, price = product
        
        await db.execute("""
            INSERT INTO cart (user_id, product_id, quantity)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, product_id) DO UPDATE SET quantity = quantity + 1
        """, (user_id, pid))
        await db.commit()
    
    await callback_query.answer(f"✅ {name} به سبد خرید اضافه شد!")

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
        text += f"• {name} × {qty} = {price * qty:,} تومان\n"
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"❌ کاهش یک {name}", callback_data=f"remove_{pid}")
        ])
    
    text += f"\n💰 جمع کل: {total:,} تومان"
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_to_menu")])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()

# ---------- حذف از سبد خرید ----------
@dp.callback_query(lambda c: c.data.startswith("remove_"))
async def remove_from_cart(callback_query: types.CallbackQuery):
    pid = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT quantity FROM cart WHERE user_id = ? AND product_id = ?",
            (user_id, pid)
        )
        row = await cursor.fetchone()
        
        if not row:
            await callback_query.answer("این محصول در سبد شما نیست!", show_alert=True)
            return
        
        if row[0] > 1:
            await db.execute(
                "UPDATE cart SET quantity = quantity - 1 WHERE user_id = ? AND product_id = ?",
                (user_id, pid)
            )
        else:
            await db.execute(
                "DELETE FROM cart WHERE user_id = ? AND product_id = ?",
                (user_id, pid)
            )
        await db.commit()
    
    await callback_query.answer("✅ تعداد کاهش یافت.")
    await show_cart(callback_query)

# ---------- تسویه حساب ----------
@dp.callback_query(lambda c: c.data == "checkout")
async def checkout(callback_query: types.CallbackQuery):
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
            await callback_query.answer("سبد خرید شما خالی است!", show_alert=True)
            return
        
        total = sum(price * qty for _, _, price, qty in items)
        
        # ایجاد سفارش جدید
        order_id = str(uuid.uuid4())
        items_list = [
            {"id": pid, "name": name, "price": price, "quantity": qty}
            for pid, name, price, qty in items
        ]
        items_json = json.dumps(items_list)
        
        await db.execute(
            "INSERT INTO orders (id, user_id, items, total_price, status) VALUES (?, ?, ?, ?, ?)",
            (order_id, user_id, items_json, total, "pending_payment")
        )
        
        # ایجاد پرداخت
        payment_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO payments (id, order_id, user_id, amount) VALUES (?, ?, ?, ?)",
            (payment_id, order_id, user_id, total)
        )
        await db.commit()
    
    try:
        zarinpal_client = zarinpal.ZarinPal(merchant_id=ZARINPAL_MERCHANT_ID)
        
        result = zarinpal_client.request(
            amount=total,
            description=f"خرید از فروشگاه - کاربر {user_id}",
            callback_url=f"{ZARINPAL_CALLBACK_URL}/callback",
            email=callback_query.from_user.username or "user@example.com"
        )
        
        if result.is_success:
            payment_url = result.payment_url
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 پرداخت از طریق درگاه", url=payment_url)],
                [InlineKeyboardButton(text="🔄 بررسی وضعیت پرداخت", callback_data=f"check_payment_{payment_id}")],
                [InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_to_menu")]
            ])
            
            await callback_query.message.edit_text(
                f"🧾 مبلغ قابل پرداخت: {total:,} تومان\n\n"
                f"📋 شماره سفارش: {order_id[:8].upper()}\n"
                f"برای پرداخت روی دکمه زیر کلیک کنید:",
                reply_markup=keyboard
            )
        else:
            await callback_query.message.edit_text(
                "❌ خطا در اتصال به درگاه پرداخت. لطفاً دوباره تلاش کنید."
            )
            print(f"خطا در درخواست پرداخت: {result.error}")
            
    except Exception as e:
        print(f"خطا در پرداخت: {e}")
        await callback_query.message.edit_text(
            "❌ خطا در فرآیند پرداخت. لطفاً دوباره تلاش کنید."
        )
    
    await callback_query.answer()

# ---------- پیگیری سفارش ----------
@dp.callback_query(lambda c: c.data == "track_order_menu")
async def track_order_menu(callback_query: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 مشاهده سفارشات من", callback_data="my_orders")],
        [InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_to_menu")]
    ])
    
    await callback_query.message.edit_text(
        "📦 سیستم پیگیری سفارش\n\n"
        "برای مشاهده سفارشات خود روی دکمه زیر کلیک کنید.",
        reply_markup=keyboard
    )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "my_orders")
async def my_orders(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, total_price, status, created_at FROM orders WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        orders = await cursor.fetchall()
    
    if not orders:
        await callback_query.message.edit_text("📭 شما هیچ سفارشی ندارید.")
        await callback_query.answer()
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    text = "📋 لیست سفارشات شما:\n\n"
    
    for order_id, total, status, created_at in orders:
        status_emoji = {
            'pending_payment': '⏳',
            'processing': '🔄',
            'approved': '✅',
            'rejected': '❌',
            'shipped': '📦',
            'delivered': '📮',
            'failed': '💔'
        }.get(status, '❓')
        
        status_text = {
            'pending_payment': 'در انتظار پرداخت',
            'processing': 'در حال پردازش',
            'approved': 'تایید شده',
            'rejected': 'رد شده',
            'shipped': 'ارسال شده',
            'delivered': 'تحویل داده شده',
            'failed': 'ناموفق'
        }.get(status, 'نامشخص')
        
        text += f"{status_emoji} سفارش {order_id[:8].upper()}\n"
        text += f"   💰 {total:,} تومان\n"
        text += f"   وضعیت: {status_text}\n"
        text += f"   📅 {created_at}\n\n"
        
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"📦 مشاهده سفارش {order_id[:8].upper()}",
                callback_data=f"view_order_{order_id}"
            )
        ])
    
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_to_menu")])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith("view_order_"))
async def view_order_detail(callback_query: types.CallbackQuery):
    order_id = callback_query.data.split("_")[2]
    user_id = callback_query.from_user.id
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT items, total_price, status, created_at, updated_at FROM orders WHERE id = ? AND user_id = ?",
            (order_id, user_id)
        )
        order = await cursor.fetchone()
        
        if not order:
            await callback_query.answer("سفارش یافت نشد!", show_alert=True)
            return
        
        items_json, total, status, created_at, updated_at = order
        items = json.loads(items_json)
        
        status_text = {
            'pending_payment': '⏳ در انتظار پرداخت',
            'processing': '🔄 در حال پردازش',
            'approved': '✅ تایید شده',
            'rejected': '❌ رد شده',
            'shipped': '📦 ارسال شده',
            'delivered': '📮 تحویل داده شده',
            'failed': '💔 ناموفق'
        }.get(status, '❓ نامشخص')
        
        items_text = "\n".join([
            f"• {item['name']} × {item['quantity']} = {item['price'] * item['quantity']:,} تومان"
            for item in items
        ])
        
        text = f"📦 جزئیات سفارش {order_id[:8].upper()}\n\n"
        text += f"📋 وضعیت: {status_text}\n"
        text += f"💰 مبلغ کل: {total:,} تومان\n"
        text += f"📅 تاریخ ثبت: {created_at}\n"
        text += f"🔄 آخرین بروزرسانی: {updated_at}\n\n"
        text += f"📦 اقلام:\n{items_text}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت به سفارشات", callback_data="my_orders")]
        ])
        
        await callback_query.message.edit_text(text, reply_markup=keyboard)
        await callback_query.answer()

# ---------- بررسی وضعیت پرداخت ----------
@dp.callback_query(lambda c: c.data.startswith("check_payment_"))
async def check_payment_status(callback_query: types.CallbackQuery):
    payment_id = callback_query.data.split("_")[2]
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT status, amount, order_id FROM payments WHERE id = ?",
            (payment_id,)
        )
        payment = await cursor.fetchone()
        
        if not payment:
            await callback_query.answer("پرداخت یافت نشد!", show_alert=True)
            return
        
        status, amount, order_id = payment
        
        if status == "paid":
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 پیگیری سفارش", callback_data=f"view_order_{order_id}")],
                [InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_to_menu")]
            ])
            await callback_query.message.edit_text(
                f"✅ پرداخت شما به مبلغ {amount:,} تومان با موفقیت انجام شد!\n"
                f"📋 شماره سفارش: {order_id[:8].upper()}",
                reply_markup=keyboard
            )
        elif status == "failed":
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 تلاش مجدد", callback_data="checkout")],
                [InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_to_menu")]
            ])
            await callback_query.message.edit_text(
                "❌ پرداخت شما ناموفق بود.\nلطفاً دوباره تلاش کنید.",
                reply_markup=keyboard
            )
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 بررسی مجدد", callback_data=f"check_payment_{payment_id}")],
                [InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_to_menu")]
            ])
            await callback_query.message.edit_text(
                "⏳ پرداخت شما در حال بررسی است.\n"
                "اگر مبلغ از حساب شما کسر شده، منتظر بمانید تا تأیید شود.",
                reply_markup=keyboard
            )
    
    await callback_query.answer()

# ---------- مدیریت سفارشات توسط ادمین ----------
@dp.callback_query(lambda c: c.data.startswith("approve_order_"))
async def approve_order(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    
    order_id = callback_query.data.split("_")[2]
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (order_id,)
        )
        await db.commit()
        
        # دریافت اطلاعات کاربر
        cursor = await db.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,))
        result = await cursor.fetchone()
        if result:
            user_id = result[0]
            await bot.send_message(
                user_id,
                f"✅ سفارش {order_id[:8].upper()} توسط ادمین تایید شد!\n"
                f"وضعیت: تایید شده\n"
                f"به زودی ارسال خواهد شد."
            )
    
    await callback_query.answer("✅ سفارش تایید شد!")
    await callback_query.message.edit_text(f"✅ سفارش {order_id[:8].upper()} تایید شد.")

@dp.callback_query(lambda c: c.data.startswith("reject_order_"))
async def reject_order(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    
    order_id = callback_query.data.split("_")[2]
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (order_id,)
        )
        await db.commit()
        
        cursor = await db.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,))
        result = await cursor.fetchone()
        if result:
            user_id = result[0]
            await bot.send_message(
                user_id,
                f"❌ سفارش {order_id[:8].upper()} توسط ادمین رد شد.\n"
                f"در صورت نیاز با پشتیبانی تماس بگیرید."
            )
    
    await callback_query.answer("❌ سفارش رد شد!")
    await callback_query.message.edit_text(f"❌ سفارش {order_id[:8].upper()} رد شد.")

@dp.callback_query(lambda c: c.data.startswith("change_status_"))
async def change_status_menu(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    
    order_id = callback_query.data.split("_")[2]
    await state.update_data(order_id=order_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 در حال پردازش", callback_data=f"set_status_processing_{order_id}")],
        [InlineKeyboardButton(text="✅ تایید شده", callback_data=f"set_status_approved_{order_id}")],
        [InlineKeyboardButton(text="📦 ارسال شده", callback_data=f"set_status_shipped_{order_id}")],
        [InlineKeyboardButton(text="📮 تحویل داده شده", callback_data=f"set_status_delivered_{order_id}")]
    ])
    
    await callback_query.message.edit_text(
        f"📦 تغییر وضعیت سفارش {order_id[:8].upper()}\n"
        "وضعیت جدید را انتخاب کنید:",
        reply_markup=keyboard
    )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith("set_status_"))
async def set_order_status(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    
    parts = callback_query.data.split("_")
    status = parts[2]
    order_id = parts[3]
    
    status_text = {
        'processing': 'در حال پردازش',
        'approved': 'تایید شده',
        'shipped': 'ارسال شده',
        'delivered': 'تحویل داده شده'
    }.get(status, status)
    
    status_emoji = {
        'processing': '🔄',
        'approved': '✅',
        'shipped': '📦',
        'delivered': '📮'
    }.get(status, '❓')
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, order_id)
        )
        await db.commit()
        
        cursor = await db.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,))
        result = await cursor.fetchone()
        if result:
            user_id = result[0]
            await bot.send_message(
                user_id,
                f"{status_emoji} وضعیت سفارش {order_id[:8].upper()} به‌روزرسانی شد!\n"
                f"وضعیت جدید: {status_text}"
            )
    
    await callback_query.answer(f"✅ وضعیت به {status_text} تغییر یافت!")
    await callback_query.message.edit_text(
        f"✅ وضعیت سفارش {order_id[:8].upper()} به {status_emoji} {status_text} تغییر یافت."
    )

# ---------- پنل ادمین ----------
@dp.callback_query(lambda c: c.data == "admin_panel")
async def admin_panel(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی به پنل ادمین ندارید!", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 مدیریت دسته‌بندی", callback_data="admin_manage_categories")],
        [InlineKeyboardButton(text="➕ افزودن محصول", callback_data="admin_add_product")],
        [InlineKeyboardButton(text="✏️ ویرایش محصول", callback_data="admin_edit_product")],
        [InlineKeyboardButton(text="🗑 حذف محصول", callback_data="admin_delete_product")],
        [InlineKeyboardButton(text="👥 مدیریت ادمین‌ها", callback_data="admin_manage_admins")],
        [InlineKeyboardButton(text="📋 لیست ادمین‌ها", callback_data="admin_list_admins")],
        [InlineKeyboardButton(text="📊 گزارش فروش", callback_data="admin_sales_report")],
        [InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_to_menu")]
    ])
    
    await callback_query.message.edit_text("🔧 پنل مدیریت فروشگاه:", reply_markup=keyboard)
    await callback_query.answer()

# ---------- مدیریت دسته‌بندی ----------
@dp.callback_query(lambda c: c.data == "admin_manage_categories")
async def manage_categories(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن دسته جدید", callback_data="admin_add_category")],
        [InlineKeyboardButton(text="🗑 حذف دسته", callback_data="admin_delete_category")],
        [InlineKeyboardButton(text="📋 مشاهده دسته‌ها", callback_data="show_categories")],
        [InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="admin_panel")]
    ])
    
    await callback_query.message.edit_text("📂 مدیریت دسته‌بندی:", reply_markup=keyboard)
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "admin_add_category")
async def add_category_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_for_category_name)
    await callback_query.message.edit_text(
        "📂 نام دسته جدید را وارد کنید:\n"
        "(برای دسته‌بندی اصلی، '0' را برای والد وارد کنید)"
    )
    await callback_query.answer()

@dp.message(AdminStates.waiting_for_category_name)
async def add_category_name(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("شما دسترسی ندارید!")
        await state.clear()
        return
    
    await state.update_data(category_name=message.text)
    await state.set_state(AdminStates.waiting_for_category_parent)
    await message.answer(
        "آی‌دی دسته والد را وارد کنید (0 برای بدون والد):\n\n"
        "📋 لیست دسته‌ها:"
    )
    
    # نمایش لیست دسته‌ها
    categories = await get_category_tree()
    text = ""
    for cat_id, name, level in categories:
        indent = "  " * level
        text += f"{indent}📁 {name} (ID: {cat_id})\n"
    await message.answer(text or "هیچ دسته‌ای وجود ندارد.")

@dp.message(AdminStates.waiting_for_category_parent)
async def add_category_parent(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("شما دسترسی ندارید!")
        await state.clear()
        return
    
    try:
        parent_id = int(message.text)
        if parent_id == 0:
            parent_id = None
    except ValueError:
        await message.answer("لطفاً یک عدد معتبر وارد کنید.")
        return
    
    data = await state.get_data()
    name = data['category_name']
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO categories (name, parent_id) VALUES (?, ?)",
            (name, parent_id)
        )
        await db.commit()
    
    await state.clear()
    await message.answer(f"✅ دسته '{name}' با موفقیت اضافه شد!")

@dp.callback_query(lambda c: c.data == "admin_delete_category")
async def delete_category_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    
    categories = await get_category_tree()
    text = "🗑 حذف دسته\n\nآی‌دی دسته مورد نظر را وارد کنید:\n\n"
    for cat_id, name, level in categories:
        indent = "  " * level
        text += f"{indent}📁 {name} (ID: {cat_id})\n"
    
    await state.set_state(AdminStates.waiting_for_delete_id)
    await callback_query.message.edit_text(text)
    await callback_query.answer()

# ---------- افزودن محصول توسط ادمین ----------
@dp.callback_query(lambda c: c.data == "admin_add_product")
async def admin_add_product_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_for_product_name)
    await callback_query.message.edit_text("📦 نام محصول را وارد کنید:")
    await callback_query.answer()

@dp.message(AdminStates.waiting_for_product_name)
async def add_product_name(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("شما دسترسی ندارید!")
        await state.clear()
        return
    
    await state.update_data(name=message.text)
    await state.set_state(AdminStates.waiting_for_product_price)
    await message.answer("💰 قیمت محصول (به تومان) را وارد کنید:")

@dp.message(AdminStates.waiting_for_product_price)
async def add_product_price(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("شما دسترسی ندارید!")
        await state.clear()
        return
    
    try:
        price = int(message.text.replace(',', ''))
        if price <= 0:
            await message.answer("قیمت باید بزرگتر از 0 باشد.")
            return
    except ValueError:
        await message.answer("لطفاً یک عدد معتبر وارد کنید.")
        return
    
    await state.update_data(price=price)
    await state.set_state(AdminStates.waiting_for_product_category)
    await message.answer(
        "📂 آی‌دی دسته محصول را وارد کنید:\n\n"
        "📋 لیست دسته‌ها:"
    )
    
    categories = await get_category_tree()
    text = ""
    for cat_id, name, level in categories:
        indent = "  " * level
        text += f"{indent}📁 {name} (ID: {cat_id})\n"
    await message.answer(text or "هیچ دسته‌ای وجود ندارد. ابتدا دسته ایجاد کنید.")

@dp.message(AdminStates.waiting_for_product_category)
async def add_product_category(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("شما دسترسی ندارید!")
        await state.clear()
        return
    
    try:
        category_id = int(message.text)
    except ValueError:
        await message.answer("لطفاً یک عدد معتبر وارد کنید.")
        return
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,))
        if not await cursor.fetchone():
            await message.answer("دسته مورد نظر یافت نشد. لطفاً مجدداً وارد کنید.")
            return
    
    await state.update_data(category_id=category_id)
    await state.set_state(AdminStates.waiting_for_product_description)
    await message.answer("📝 توضیحات محصول را وارد کنید (اختیاری، برای رد کردن '0' را وارد کنید):")

@dp.message(AdminStates.waiting_for_product_description)
async def add_product_description(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("شما دسترسی ندارید!")
        await state.clear()
        return
    
    description = message.text if message.text != '0' else None
    await state.update_data(description=description)
    
    data = await state.get_data()
    name = data['name']
    price = data['price']
    category_id = data['category_id']
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO products (name, price, description, category_id) VALUES (?, ?, ?, ?)",
            (name, price, description, category_id)
        )
        await db.commit()
    
    await state.clear()
    await message.answer(f"✅ محصول '{name}' با موفقیت اضافه شد!")

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
        cursor = await db.execute("SELECT name, price, description, category_id FROM products WHERE id = ?", (pid,))
        product = await cursor.fetchone()
        if not product:
            await message.answer("محصولی با این آی‌دی وجود ندارد.")
            await state.clear()
            return
        
        await state.update_data(edit_id=pid)
        await state.set_state(AdminStates.waiting_for_edit_field)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="نام", callback_data="edit_field_name")],
            [InlineKeyboardButton(text="قیمت", callback_data="edit_field_price")],
            [InlineKeyboardButton(text="توضیحات", callback_data="edit_field_description")],
            [InlineKeyboardButton(text="دسته", callback_data="edit_field_category")]
        ])
        
        await message.answer(
            f"📦 اطلاعات فعلی:\n"
            f"نام: {product[0]}\n"
            f"قیمت: {product[1]:,} تومان\n"
            f"توضیحات: {product[2] or 'ندارد'}\n"
            f"دسته: {product[3]}\n\n"
            "کدام فیلد را می‌خواهید ویرایش کنید؟",
            reply_markup=keyboard
        )

@dp.callback_query(lambda c: c.data.startswith("edit_field_"))
async def edit_field_selection(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    
    field = callback_query.data.split("_")[2]
    await state.update_data(edit_field=field)
    await state.set_state(AdminStates.waiting_for_edit_value)
    
    field_names = {
        'name': 'نام',
        'price': 'قیمت (به تومان)',
        'description': 'توضیحات',
        'category': 'آی‌دی دسته'
    }
    
    await callback_query.message.edit_text(f"مقدار جدید برای '{field_names.get(field, field)}' را وارد کنید:")
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
    
    try:
        if field == 'price':
            value = int(value.replace(',', ''))
            if value <= 0:
                await message.answer("قیمت باید بزرگتر از 0 باشد.")
                return
        elif field == 'category':
            value = int(value)
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute("SELECT 1 FROM categories WHERE id = ?", (value,))
                if not await cursor.fetchone():
                    await message.answer("دسته مورد نظر یافت نشد.")
                    return
    except ValueError:
        await message.answer("لطفاً یک مقدار معتبر وارد کنید.")
        return
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE products SET {field} = ? WHERE id = ?", (value, pid))
        await db.commit()
    
    await state.clear()
    await message.answer(f"✅ فیلد با موفقیت به‌روزرسانی شد.")

# ---------- حذف محصول ----------
@dp.callback_query(lambda c: c.data == "admin_delete_product")
async def delete_product_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_for_delete_id)
    await callback_query.message.edit_text("🗑 آی‌دی محصول مورد نظر برای حذف را وارد کنید:")
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
        product = await cursor.fetchone()
        if not product:
            await message.answer("محصولی با این آی‌دی وجود ندارد.")
            await state.clear()
            return
        
        await db.execute("DELETE FROM products WHERE id = ?", (pid,))
        await db.commit()
    
    await state.clear()
    await message.answer(f"✅ محصول '{product[0]}' با آی‌دی {pid} حذف شد.")

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

# ---------- گزارش فروش ----------
@dp.callback_query(lambda c: c.data == "admin_sales_report")
async def sales_report(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("شما دسترسی ندارید!", show_alert=True)
        return
    
    async with aiosqlite.connect(DB_PATH) as db:
        # آمار کلی سفارشات
        cursor = await db.execute("""
            SELECT 
                COUNT(*) as total_orders,
                SUM(CASE WHEN status IN ('approved', 'shipped', 'delivered') THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'pending_payment' THEN 1 ELSE 0 END) as pending_payment,
                SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing,
                SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
                SUM(total_price) as total_revenue
            FROM orders
            WHERE status IN ('approved', 'shipped', 'delivered')
        """)
        stats = await cursor.fetchone()
        total_orders, completed, pending_payment, processing, rejected, total_revenue = stats
        
        # آخرین 5 سفارش
        cursor = await db.execute("""
            SELECT id, user_id, total_price, status, created_at
            FROM orders
            ORDER BY created_at DESC
            LIMIT 5
        """)
        recent_orders = await cursor.fetchall()
    
    text = "📊 گزارش فروش:\n\n"
    text += f"📌 کل سفارشات: {total_orders or 0}\n"
    text += f"✅ تکمیل شده: {completed or 0}\n"
    text += f"⏳ در انتظار پرداخت: {pending_payment or 0}\n"
    text += f"🔄 در حال پردازش: {processing or 0}\n"
    text += f"❌ رد شده: {rejected or 0}\n"
    text += f"💰 درآمد کل: {total_revenue or 0:,} تومان\n\n"
    
    text += "📋 آخرین سفارشات:\n"
    for order_id, user_id, total, status, created_at in recent_orders:
        status_emoji = {
            'pending_payment': '⏳',
            'processing': '🔄',
            'approved': '✅',
            'rejected': '❌',
            'shipped': '📦',
            'delivered': '📮'
        }.get(status, '❓')
        text += f"{status_emoji} {order_id[:8].upper()} - کاربر {user_id} - {total:,} تومان\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="admin_panel")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()

# ---------- بازگشت به منو ----------
@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback_query: types.CallbackQuery):
    await send_menu(callback_query.message, edit=True)
    await callback_query.answer()

# ---------- اجرای اصلی ----------
async def main():
    print("🤖 ربات در حال راه‌اندازی...")
    await init_db()
    await start_health_server()
    print("✅ ربات روشن شد!")
    
    while True:
        try:
            await dp.start_polling(bot)
        except Exception as e:
            print(f"❌ خطا رخ داد: {e}")
            print("🔄 تلاش مجدد در 5 ثانیه...")
            await asyncio.sleep(5)
            continue

if __name__ == "__main__":
    asyncio.run(main())
