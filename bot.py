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
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    ConversationHandler,
)

# === KONFIGURACJA ===
TOKEN = "6587025285:AAHHMBAH9GzXxUp4aof-0A549xdpLwLMQu4"
ADMIN_IDS = [1877239478]
DB_FILE = "products.db"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === STANY KONWERSACJI ===
EDIT_PRICE = 1

# === INICJALIZACJA BAZY ===
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            price TEXT,
            image TEXT
        )
    """)
    conn.commit()
    conn.close()

# === POMOCNICZE DB ===
def add_product_db(name, price, image):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO products (name, price, image) VALUES (?, ?, ?)",
              (name, price, image))
    conn.commit()
    conn.close()


def remove_product_db(prod_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = ?", (prod_id,))
    conn.commit()
    conn.close()


def update_price_db(name, new_price):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE products SET price = ? WHERE name = ?", (new_price, name))
    conn.commit()
    conn.close()


def list_products_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name, price, image FROM products")
    items = c.fetchall()
    conn.close()
    return items

# === ADMIN CHECK ===
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# === HANDLERY PUBLICZNE ===

def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("🛍 Sprawdź dostępne produkty", callback_data="show_products")],
        [InlineKeyboardButton("💰 Sprawdź cennik", callback_data="show_prices")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Witaj! Wybierz co chcesz zrobić:", reply_markup=reply_markup)


def callback_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    if query.data == "show_products":
        items = list_products_db()
        if not items:
            query.edit_message_text("Brak produktów w ofercie.")
            return
        media = [InputMediaPhoto(item[3], caption=item[1]) for item in items]
        context.bot.send_media_group(chat_id=query.message.chat_id, media=media)

    elif query.data == "show_prices":
        items = list_products_db()
        if not items:
            query.edit_message_text("Brak produktów w ofercie.")
            return
        text = "💵 *Cennik produktów:*\n\n"
        for _, name, price, _ in items:
            text += f"• *{name}* – {price}\n"
        query.edit_message_text(text, parse_mode="Markdown")

# === HANDLERY ADMINA ===

def add_product(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_admin(user.id):
        return update.message.reply_text("🚫 Nie masz uprawnień.")

    args = " ".join(context.args)
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        try:
            name, price = [x.strip() for x in args.split("|")]
        except ValueError:
            return update.message.reply_text("Użycie: /add_product nazwa|cena + załącz obrazek")
        image = file_id
    else:
        try:
            name, price, image = [x.strip() for x in args.split("|")]
        except ValueError:
            return update.message.reply_text("Użycie: /add_product nazwa|cena|url_obrazka lub załącz obrazek")

    add_product_db(name, price, image)
    update.message.reply_text(f"✅ Dodano produkt *{name}*.", parse_mode="Markdown")


def list_products_admin(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_admin(user.id):
        return update.message.reply_text("🚫 Nie masz uprawnień.")

    items = list_products_db()
    if not items:
        return update.message.reply_text("Brak produktów.")
    for prod_id, name, price, _ in items:
        keyboard = [
            InlineKeyboardButton("✏️ Edytuj cenę", callback_data=f"admin_edit_{prod_id}"),
            InlineKeyboardButton("🗑 Usuń", callback_data=f"admin_remove_{prod_id}"),
        ]
        markup = InlineKeyboardMarkup([keyboard])
        update.message.reply_text(f"*{name}* – {price}", parse_mode="Markdown", reply_markup=markup)


def callback_admin(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user = update.effective_user
    if not is_admin(user.id):
        return query.edit_message_text("🚫 Nie masz uprawnień.")

    data = query.data
    if data.startswith("admin_remove_"):
        prod_id = int(data.split("_")[-1])
        remove_product_db(prod_id)
        query.edit_message_text("✅ Produkt usunięty.")
        return ConversationHandler.END

    elif data.startswith("admin_edit_"):
        prod_id = int(data.split("_")[-1])
        context.user_data['edit_id'] = prod_id
        # pobierz nazwę
        items = list_products_db()
        name = next((item[1] for item in items if item[0] == prod_id), None)
        query.message.reply_text(
            f"Podaj nową cenę dla *{name}*:",
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True)
        )
        return EDIT_PRICE


def admin_receive_price(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_admin(user.id):
        update.message.reply_text("🚫 Nie masz uprawnień.")
        return ConversationHandler.END

    text = update.message.text.strip()
    prod_id = context.user_data.get('edit_id')
    if not prod_id:
        update.message.reply_text("Coś poszło nie tak.")
        return ConversationHandler.END

    # aktualizacja
    items = list_products_db()
    name = next((item[1] for item in items if item[0] == prod_id), None)
    if not name:
        update.message.reply_text("Nie znaleziono produktu.")
        return ConversationHandler.END
    update_price_db(name, text)
    update.message.reply_text(f"✅ Zaktualizowano cenę *{name}* → *{text}*", parse_mode="Markdown")
    context.user_data.pop('edit_id', None)
    return ConversationHandler.END

# === URUCHAMIANIE BOTA ===

def main():
    init_db()
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    # publiczne
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(callback_menu, pattern="^(show_).*$"))

    # admin
    dp.add_handler(CommandHandler("add_product", add_product))
    dp.add_handler(CommandHandler("list_products_admin", list_products_admin))

    # dialog edycji ceny
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callback_admin, pattern="^(admin_).*$")],
        states={
            EDIT_PRICE: [MessageHandler(Filters.reply & ~Filters.command, admin_receive_price)],
        },
        fallbacks=[],
        per_user=True,
    )
    dp.add_handler(conv)

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
