import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

# === KONFIGURACJA ===
TOKEN = "6587025285:AAHHMBAH9GzXxUp4aof-0A549xdpLwLMQu4"
ADMIN_IDS = [1877239478]
DB_FILE = "products.db"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === STANY KONWERSACJI ===
ADD_PRODUCT, EDIT_NAME, EDIT_PRICE, EDIT_DESC = range(4)

# === INICJALIZACJA BAZY ===
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            price TEXT,
            image TEXT,
            description TEXT
        )
    """
    )
    conn.commit()
    conn.close()

# === OPERACJE NA BAZIE ===
def add_product_db(name: str, price: str, image: str) -> None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO products (name, price, image, description) VALUES (?, ?, ?, "
        "COALESCE((SELECT description FROM products WHERE name=?), ''))",
        (name, price, image, name)
    )
    conn.commit()
    conn.close()

def remove_product_db(prod_id: int) -> None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = ?", (prod_id,))
    conn.commit()
    conn.close()

def update_name_db(prod_id: int, new_name: str) -> None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE products SET name = ? WHERE id = ?", (new_name, prod_id))
    conn.commit()
    conn.close()

def update_price_db(prod_id: int, new_price: str) -> None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE products SET price = ? WHERE id = ?", (new_price, prod_id))
    conn.commit()
    conn.close()

def update_desc_db(prod_id: int, new_desc: str) -> None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE products SET description = ? WHERE id = ?", (new_desc, prod_id))
    conn.commit()
    conn.close()

def list_products_db() -> list:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name, price, image, description FROM products")
    items = c.fetchall()
    conn.close()
    return items

# === SPRAWDZANIE UPRAWNIEŃ ===
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# === HANDLERY PUBLICZNE ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    buttons = [
        [InlineKeyboardButton("🛍 Produkty", callback_data="show_products")],
        [InlineKeyboardButton("💰 Cennik", callback_data="show_prices")],
        [InlineKeyboardButton("✉️ Kontakt", url="https://t.me/zenpuffs77")]
    ]
    if is_admin(update.effective_user.id):
        buttons.append([InlineKeyboardButton("🔧 Panel admina", callback_data="admin_panel")])
    await update.message.reply_text(
        "Witaj! Wybierz opcję:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def callback_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "show_products":
        items = list_products_db()
        if not items:
            await query.edit_message_text("Brak produktów.")
            return
        for prod_id, name, price, image, desc in items:
            caption = f"*{name}*"
            if desc:
                caption += "\n\n" + desc
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=image,
                caption=caption,
                parse_mode="Markdown"
            )
    elif data == "show_prices":
        items = list_products_db()
        text = "💵 *Cennik produktów:*\n\n"
        for _, name, price, _, _ in items:
            text += f"• *{name}* – {price}\n"
        await query.edit_message_text(text, parse_mode="Markdown")
    elif data == "admin_panel" and is_admin(query.from_user.id):
        buttons = [
            [InlineKeyboardButton("➕ Dodaj produkt", callback_data="admin_add")],
            [InlineKeyboardButton("📋 Lista", callback_data="admin_list")]
        ]
        await query.edit_message_text("Panel administratora:", reply_markup=InlineKeyboardMarkup(buttons))

# === HANDLERY ADMINA ===
async def admin_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.message.reply_text(
        "Podaj dane produktu: nazwa|cena|url lub prześlij zdjęcie z opisem nazwa|cena",
        reply_markup=ForceReply(selective=True)
    )
    return ADD_PRODUCT

async def admin_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    items = list_products_db()
    if not items:
        await update.callback_query.message.reply_text("Brak produktów.")
        return
    for prod_id, name, price, _, _ in items:
        buttons = [
            InlineKeyboardButton("✏️ Nazwa", callback_data=f"admin_name_{prod_id}"),
            InlineKeyboardButton("✏️ Cena", callback_data=f"admin_price_{prod_id}"),
            InlineKeyboardButton("✏️ Opis", callback_data=f"admin_desc_{prod_id}"),
            InlineKeyboardButton("🗑 Usuń", callback_data=f"admin_remove_{prod_id}"),
        ]
        await update.callback_query.message.reply_text(
            f"*{name}* – {price}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([buttons])
        )

async def admin_remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    prod_id = int(query.data.split("_")[-1])
    remove_product_db(prod_id)
    await query.edit_message_text("✅ Produkt usunięty.")

async def admin_product_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = update.callback_query.data
    prod_id = int(data.split("_")[-1])
    context.user_data['prod_id'] = prod_id
    if data.startswith("admin_name_"):
        await update.callback_query.message.reply_text("Podaj nową nazwę:", reply_markup=ForceReply(selective=True))
        return EDIT_NAME
    if data.startswith("admin_price_"):
        await update.callback_query.message.reply_text("Podaj nową cenę:", reply_markup=ForceReply(selective=True))
        return EDIT_PRICE
    if data.startswith("admin_desc_"):
        await update.callback_query.message.reply_text("Podaj nowy opis:", reply_markup=ForceReply(selective=True))
        return EDIT_DESC

async def admin_receive_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text or ""
    photo = update.message.photo[-1].file_id if update.message.photo else None
    parts = text.strip().split("|", 2)
    if photo and len(parts) >= 2:
        name, price = parts[0].strip(), parts[1].strip()
        image = photo
    elif len(parts) == 3:
        name, price, image = (p.strip() for p in parts)
    else:
        await update.message.reply_text("Błędne dane, spróbuj ponownie.")
        return ADD_PRODUCT
    add_product_db(name, price, image)
    await update.message.reply_text(f"✅ Dodano produkt *{name}*.", parse_mode="Markdown")
    return ConversationHandler.END

async def admin_receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_name = update.message.text.strip()
    prod_id = context.user_data.pop('prod_id')
    update_name_db(prod_id, new_name)
    await update.message.reply_text(f"✅ Zmieniono nazwę na *{new_name}*.", parse_mode="Markdown")
    return ConversationHandler.END

async def admin_receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_price = update.message.text.strip()
    prod_id = context.user_data.pop('prod_id')
    update_price_db(prod_id, new_price)
    await update.message.reply_text(f"✅ Zmieniono cenę na *{new_price}*.", parse_mode="Markdown")
    return ConversationHandler.END

async def admin_receive_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_desc = update.message.text.strip()
    prod_id = context.user_data.pop('prod_id')
    update_desc_db(prod_id, new_desc)
    await update.message.reply_text("✅ Zmieniono opis.")
    return ConversationHandler.END

# === URUCHAMIANIE BOTA ===

def main() -> None:
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

        # publiczne
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_main, pattern="^(show_products|show_prices|admin_panel)$"))
    # komenda dodawania produktów przez slash
    app.add_handler(CommandHandler("add_product", admin_receive_add))

    # admin panel
    app.add_handler(CallbackQueryHandler(admin_add_callback, pattern="^admin_add$"))
    app.add_handler(CallbackQueryHandler(admin_list_callback, pattern="^admin_list$"))
    app.add_handler(CallbackQueryHandler(admin_remove_callback, pattern="^admin_remove_"))

    # conversation for add/edit
    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_add_callback, pattern="^admin_add$"),
            CallbackQueryHandler(admin_product_entry, pattern="^admin_(name|price|desc)_"),
        ],
        states={
            ADD_PRODUCT: [MessageHandler(filters.TEXT | filters.PHOTO, admin_receive_add)],
            EDIT_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_name)],
            EDIT_PRICE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_price)],
            EDIT_DESC:    [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_desc)],
        },
        fallbacks=[],
        per_user=True,
        per_message=True,
    )
    app.add_handler(conv)

    app.run_polling()

if __name__ == "__main__":
    main()
