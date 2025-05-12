import sqlite3
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    ForceReply,
)
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
TOKEN = "<TWÓJ_TOKEN_Z_BOTFATHER>"
ADMIN_IDS = [123456789]
DB_FILE = "products.db"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === STANY KONWERSACJI ===
EDIT_PRICE, EDIT_DESC = 1, 2

# === INICJALIZACJA BAZY ===
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # utworzenie tabeli z kolumną opisu
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            price TEXT,
            image TEXT,
            description TEXT
        )
    """)
    # dodanie kolumny description, jeśli nie istnieje
    try:
        c.execute("ALTER TABLE products ADD COLUMN description TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

# === POMOCNICZE OPERACJE NA BAZIE ===
def add_product_db(name: str, price: str, image: str) -> None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # jeśli produkt istnieje, aktualizuj cenę i obraz, pozostaw opis
    c.execute("SELECT id FROM products WHERE name = ?", (name,))
    if c.fetchone():
        c.execute(
            "UPDATE products SET price = ?, image = ? WHERE name = ?",
            (price, image, name)
        )
    else:
        c.execute(
            "INSERT INTO products (name, price, image, description) VALUES (?, ?, ?, '')",
            (name, price, image)
        )
    conn.commit()
    conn.close()


def remove_product_db(prod_id: int) -> None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = ?", (prod_id,))
    conn.commit()
    conn.close()


def update_price_db(name: str, new_price: str) -> None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE products SET price = ? WHERE name = ?", (new_price, name))
    conn.commit()
    conn.close()


def update_description_db(prod_id: int, description: str) -> None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE products SET description = ? WHERE id = ?", (description, prod_id))
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
    keyboard = [
        [InlineKeyboardButton("🛍 Sprawdź dostępne produkty", callback_data="show_products")],
        [InlineKeyboardButton("💰 Sprawdź cennik", callback_data="show_prices")],
    ]
    await update.message.reply_text("Witaj! Wybierz co chcesz zrobić:", reply_markup=InlineKeyboardMarkup(keyboard))

async def callback_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    items = list_products_db()

    if data == "show_products":
        if not items:
            await query.edit_message_text("Brak produktów w ofercie.")
            return
        media = []
        for prod_id, name, price, image, desc in items:
            caption = f"*{name}*"
            if desc:
                caption += f"\n{desc}"
            media.append(InputMediaPhoto(media=image, caption=caption, parse_mode="Markdown"))
        await context.bot.send_media_group(chat_id=query.message.chat_id, media=media)

    elif data == "show_prices":
        if not items:
            await query.edit_message_text("Brak produktów w ofercie.")
            return
        text = "💵 *Cennik produktów:*\n\n"
        for _, name, price, _, _ in items:
            text += f"• *{name}* – {price}\n"
        await query.edit_message_text(text, parse_mode="Markdown")

# === HANDLERY ADMINISTRATORA ===
async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("🚫 Nie masz uprawnień.")
        return

    args = " ".join(context.args)
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        try:
            name, price = [x.strip() for x in args.split("|")]
        except ValueError:
            await update.message.reply_text("Użycie: /add_product nazwa|cena + załącz obrazek")
            return
        image = file_id
    else:
        try:
            name, price, image = [x.strip() for x in args.split("|")]
        except ValueError:
            await update.message.reply_text("Użycie: /add_product nazwa|cena|url_obrazka lub załącz obrazek")
            return

    add_product_db(name, price, image)
    await update.message.reply_text(f"✅ Dodano produkt *{name}*.", parse_mode="Markdown")

async def list_products_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("🚫 Nie masz uprawnień.")
        return

    items = list_products_db()
    if not items:
        await update.message.reply_text("Brak produktów.")
        return
    for prod_id, name, price, _, _ in items:
        keyboard = [
            InlineKeyboardButton("✏️ Edytuj cenę", callback_data=f"admin_edit_{prod_id}"),
            InlineKeyboardButton("✍️ Edytuj opis", callback_data=f"admin_desc_{prod_id}"),
            InlineKeyboardButton("🗑 Usuń", callback_data=f"admin_remove_{prod_id}"),
        ]
        await update.message.reply_text(
            f"*{name}* – {price}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([keyboard])
        )

async def callback_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if not is_admin(user.id):
        await query.edit_message_text("🚫 Nie masz uprawnień.")
        return ConversationHandler.END

    data = query.data
    prod_id = int(data.split("_")[-1])
    # usuń produkt
    if data.startswith("admin_remove_"):
        remove_product_db(prod_id)
        await query.edit_message_text("✅ Produkt usunięty.")
        return ConversationHandler.END

    # edytuj cenę
    if data.startswith("admin_edit_"):
        context.user_data['edit_id'] = prod_id
        items = list_products_db()
        name = next((item[1] for item in items if item[0] == prod_id), None)
        await query.message.reply_text(
            f"Podaj nową cenę dla *{name}*:",
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True)
        )
        return EDIT_PRICE

    # edytuj opis
    if data.startswith("admin_desc_"):
        context.user_data['desc_id'] = prod_id
        items = list_products_db()
        name = next((item[1] for item in items if item[0] == prod_id), None)
        await query.message.reply_text(
            f"Podaj opis dla *{name}*:",
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True)
        )
        return EDIT_DESC

async def admin_receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("🚫 Nie masz uprawnień.")
        return ConversationHandler.END

    text = update.message.text.strip()
    prod_id = context.user_data.get('edit_id')
    if not prod_id:
        await update.message.reply_text("Coś poszło nie tak.")
        return ConversationHandler.END

    items = list_products_db()
    name = next((item[1] for item in items if item[0] == prod_id), None)
    update_price_db(name, text)
    await update.message.reply_text(f"✅ Zaktualizowano cenę *{name}* → *{text}*", parse_mode="Markdown")
    context.user_data.pop('edit_id', None)
    return ConversationHandler.END

async def admin_receive_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("🚫 Nie masz uprawnień.")
        return ConversationHandler.END

    text = update.message.text.strip()
    prod_id = context.user_data.get('desc_id')
    if not prod_id:
        await update.message.reply_text("Coś poszło nie tak.")
        return ConversationHandler.END

    update_description_db(prod_id, text)
    items = list_products_db()
    name = next((item[1] for item in items if item[0] == prod_id), None)
    await update.message.reply_text(f"✅ Zaktualizowano opis *{name}*.", parse_mode="Markdown")
    context.user_data.pop('desc_id', None)
    return ConversationHandler.END

# === URUCHAMIANIE BOTA ===
def main() -> None:
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    # bezpośrednia obsługa przycisków admin_
    app.add_handler(CallbackQueryHandler(callback_admin, pattern=r'^admin_'))

    # publiczne handlery
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_menu, pattern="^(show_).*$"))

    # administrowanie
    app.add_handler(CommandHandler("add_product", add_product))
    app.add_handler(CommandHandler("list_products_admin", list_products_admin))

    # dialog edycji ceny i opisu
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callback_admin, pattern="^(admin_).*$")],
        states={
            EDIT_PRICE: [MessageHandler(filters.REPLY & ~filters.COMMAND, admin_receive_price)],
            EDIT_DESC:  [MessageHandler(filters.REPLY & ~filters.COMMAND, admin_receive_desc)],
        },
        fallbacks=[],
        per_user=True,
        per_message=True,
    )
    app.add_handler(conv)

    # uruchom polling
    app.run_polling()

if __name__ == "__main__":
    main()
