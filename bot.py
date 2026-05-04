import os
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton
)
import requests
import threading
from flask import Flask
from vk_worker import send_to_vk_groups
from dotenv import load_dotenv

load_dotenv()

TG_TOKEN = os.getenv('TG_TOKEN')

# --- ПОРТ ДЛЯ AMVERA ---
raw_port = os.getenv('PORT')
try:
    PORT = int(raw_port) if raw_port and raw_port.lower() not in ('null', '', 'none') else 80
except ValueError:
    PORT = 80
# -------------------------

bot = telebot.TeleBot(TG_TOKEN)
app = Flask(__name__)

user_data = {}

# ─── Вспомогательные функции ───

def reset_webhook():
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/setWebhook?url="
        r = requests.get(url, timeout=10)
        print(f"[Webhook] Сброшен: {r.status_code}")
    except Exception as e:
        print(f"[Webhook] Ошибка: {e}")

def main_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Отправить объявление"))
    return kb

def category_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📁 Обычные группы"), KeyboardButton("⭐ Крупные группы"))
    return kb

def photo_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Закончить отправку фото ✅"))
    return kb

def confirm_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Готово ☑️"), KeyboardButton("Изменить"))
    return kb

def account_inline_kb():
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("Аксессуары", callback_data='acc_accessories'),
        InlineKeyboardButton("Автопродажа", callback_data='acc_autosale')
    )
    return kb

# ─── Обработчики ───

@bot.message_handler(commands=['start'])
def cmd_start(message):
    chat_id = message.chat.id
    user_data[chat_id] = {'state': 'main'}
    bot.send_message(chat_id, "👋 Привет! Нажми кнопку ниже.", reply_markup=main_kb())

@bot.message_handler(func=lambda m: m.text == "Отправить объявление")
def send_ad(message):
    chat_id = message.chat.id
    user_data[chat_id] = {
        'state': 'account',
        'photos': [], 'text': '', 'category': None, 'account': None
    }
    bot.send_message(
        chat_id,
        "Через какой аккаунт отправляем?",
        reply_markup=account_inline_kb()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('acc_'))
def choose_account(call):
    chat_id = call.message.chat.id
    if user_data.get(chat_id, {}).get('state') != 'account':
        return

    account = 'accessories' if call.data == 'acc_accessories' else 'autosale'
    user_data[chat_id]['account'] = account
    user_data[chat_id]['state'] = 'category'

    name = "Аксессуары" if account == 'accessories' else "Дашин"
    print(f"[ACCOUNT] Пользователь {chat_id} выбрал: {name}")

    bot.answer_callback_query(call.id, f"Выбран: {name}")
    bot.edit_message_text(
        f"✅ Аккаунт: <b>{name}</b>\n\nТеперь выбери категорию групп:",
        chat_id=chat_id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    bot.send_message(chat_id, "Выбери категорию:", reply_markup=category_kb())

@bot.message_handler(func=lambda m: m.text in ["📁 Обычные группы", "⭐ Крупные группы"])
def choose_category(message):
    chat_id = message.chat.id
    if user_data.get(chat_id, {}).get('state') != 'category':
        return

    category = 'usual' if 'Обычные' in message.text else 'large'
    user_data[chat_id]['category'] = category
    user_data[chat_id]['state'] = 'photo'

    print(f"[CATEGORY] Пользователь {chat_id} выбрал {category}")
    bot.send_message(
        chat_id,
        "📷 Отправь фото (до 10 шт.). Когда закончишь — нажми кнопку ниже.",
        reply_markup=photo_kb()
    )

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id
    if user_data.get(chat_id, {}).get('state') != 'photo':
        return

    photos = user_data[chat_id]['photos']
    if len(photos) >= 10:
        return bot.send_message(chat_id, "❌ Лимит 10 фото. Нажми «Закончить отправку фото ✅»")

    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded = bot.download_file(file_info.file_path)

    tmp = f"temp/{chat_id}"
    os.makedirs(tmp, exist_ok=True)
    path = os.path.join(tmp, f"photo_{len(photos)}.jpg")
    with open(path, 'wb') as f:
        f.write(downloaded)

    photos.append(path)
    print(f"[PHOTO] Сохранено: {path} | Размер: {os.path.getsize(path)} байт")
    bot.send_message(
        chat_id,
        f"📷 Фото {len(photos)}/10. Можешь ещё или нажать «Закончить отправку фото ✅»",
        reply_markup=photo_kb()
    )

@bot.message_handler(func=lambda m: m.text == "Закончить отправку фото ✅")
def finish_photos(message):
    chat_id = message.chat.id
    if user_data.get(chat_id, {}).get('state') != 'photo':
        return
    if not user_data[chat_id]['photos']:
        return bot.send_message(chat_id, "❌ Ни одного фото. Отправь хотя бы одно.")

    user_data[chat_id]['state'] = 'text'
    print(f"[FINISH] Файлы: {user_data[chat_id]['photos']}")
    bot.send_message(chat_id, "✏️ Теперь отправь текст объявления:", reply_markup=ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: user_data.get(m.chat.id, {}).get('state') == 'text')
def handle_text(message):
    chat_id = message.chat.id
    user_data[chat_id]['text'] = message.text
    user_data[chat_id]['state'] = 'confirm'

    preview = (
        f"📋 Предпросмотр:\n\n"
        f"{message.text}\n\n"
        f"📷 Фото: {len(user_data[chat_id]['photos'])}\n"
        f"👤 Аккаунт: {'Аксессуары' if user_data[chat_id]['account'] == 'accessories' else 'Автопродажа'}"
    )
    bot.send_message(chat_id, preview, reply_markup=confirm_kb())

@bot.message_handler(func=lambda m: m.text == "Готово ☑️")
def confirm_send(message):
    chat_id = message.chat.id
    if user_data.get(chat_id, {}).get('state') != 'confirm':
        return

    data = user_data[chat_id]
    account = data.get('account', 'accessories')
    acc_name = 'Аксессуары' if account == 'accessories' else 'Автопродажа'

    print(f"[CONFIRM] Отправка: {len(data['photos'])} фото, аккаунт: {acc_name}")

    for p in data['photos']:
        exists = os.path.exists(p)
        size = os.path.getsize(p) if exists else 0
        print(f"[CHECK] {p} | exists={exists} | size={size}")

    bot.send_message(chat_id, f"⏳ Отправляю через <b>{acc_name}</b>...", parse_mode='HTML')

    try:
        report = send_to_vk_groups(
            data['text'],
            data['photos'],
            data['category'],
            account=account
        )
        bot.send_message(chat_id, f"📋 Отправка завершена!\n\n{report}", reply_markup=main_kb())
    except Exception as e:
        err_msg = str(e)
        print(f"[FATAL] {err_msg}")
        bot.send_message(chat_id, f"🔥 Ошибка:\n\n{err_msg}", reply_markup=main_kb())
    finally:
        for p in data.get('photos', []):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except:
                pass
        user_data[chat_id] = {'state': 'main'}

@bot.message_handler(func=lambda m: m.text == "Изменить")
def reset_ad(message):
    chat_id = message.chat.id
    if chat_id in user_data:
        for p in user_data[chat_id].get('photos', []):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except:
                pass

    user_data[chat_id] = {
        'state': 'account',
        'photos': [], 'text': '', 'category': None, 'account': None
    }
    print(f"[RESET] Пользователь {chat_id} сбросил объявление")
    bot.send_message(
        chat_id,
        "Через какой аккаунт отправляем?",
        reply_markup=account_inline_kb()
    )

@bot.message_handler(func=lambda m: True)
def fallback(message):
    chat_id = message.chat.id
    state = user_data.get(chat_id, {}).get('state', 'unknown')
    print(f"[FALLBACK] Пользователь {chat_id}, состояние '{state}', текст: {message.text}")
    bot.send_message(
        chat_id,
        "❓ Нажми /start если что-то пошло не так.",
        reply_markup=main_kb()
    )

@app.route('/')
def index():
    return "OK", 200

def run_bot():
    reset_webhook()
    print("[Bot] Старт polling...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

if __name__ == '__main__':
    print(f"[Server] Flask на порту {PORT}")
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=PORT)
