import os
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
import requests
import threading
from flask import Flask
from vk_worker import send_to_vk_groups
from dotenv import load_dotenv

load_dotenv()

TG_TOKEN = os.getenv('TG_TOKEN')
PORT = int(os.getenv('PORT', 8080))

bot = telebot.TeleBot(TG_TOKEN)
app = Flask(__name__)

# Хранилище состояний пользователей: {chat_id: {...}}
user_data = {}

# ─── Вспомогательные функции ───

def reset_webhook():
    """Сброс вебхука перед запуском polling (решает ошибку 409)."""
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/setWebhook?url="
        r = requests.get(url, timeout=10)
        print(f"[Webhook] Сброшен. Ответ: {r.status_code}")
    except Exception as e:
        print(f"[Webhook] Ошибка сброса: {e}")

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

# ─── Обработчики ───

@bot.message_handler(commands=['start'])
def cmd_start(message):
    chat_id = message.chat.id
    user_data[chat_id] = {'state': 'main'}
    bot.send_message(
        chat_id,
        "👋 Привет! Я бот для публикации объявлений в группы ВКонтакте.\n\n"
        "Нажмите кнопку ниже, чтобы начать.",
        reply_markup=main_kb()
    )

@bot.message_handler(func=lambda m: m.text == "Отправить объявление")
def send_ad(message):
    chat_id = message.chat.id
    user_data[chat_id] = {'state': 'category', 'photos': [], 'text': '', 'category': None}
    bot.send_message(chat_id, "Выберите категорию групп:", reply_markup=category_kb())

@bot.message_handler(func=lambda m: m.text in ["📁 Обычные группы", "⭐ Крупные группы"])
def choose_category(message):
    chat_id = message.chat.id
    if chat_id not in user_data or user_data[chat_id].get('state') != 'category':
        return

    category = 'usual' if 'Обычные' in message.text else 'large'
    user_data[chat_id]['category'] = category
    user_data[chat_id]['state'] = 'photo'

    bot.send_message(
        chat_id,
        "📷 Отправьте фото (до 10 шт.).\nКогда закончите — нажмите кнопку ниже.",
        reply_markup=photo_kb()
    )

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id
    if chat_id not in user_data or user_data[chat_id].get('state') != 'photo':
        return

    photos = user_data[chat_id]['photos']
    if len(photos) >= 10:
        bot.send_message(chat_id, "❌ Достигнут лимит в 10 фото. Нажмите «Закончить отправку фото ✅»")
        return

    # Берём фото максимального качества (последний элемент в списке)
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    temp_dir = f"temp/{chat_id}"
    os.makedirs(temp_dir, exist_ok=True)

    file_path = os.path.join(temp_dir, f"photo_{len(photos)}.jpg")
    with open(file_path, 'wb') as f:
        f.write(downloaded_file)

    photos.append(file_path)
    user_data[chat_id]['photos'] = photos

    bot.send_message(
        chat_id,
        f"📷 Фото {len(photos)}/10 получено. Можете отправить ещё или нажать «Закончить отправку фото ✅»",
        reply_markup=photo_kb()
    )

@bot.message_handler(func=lambda m: m.text == "Закончить отправку фото ✅")
def finish_photos(message):
    chat_id = message.chat.id
    if chat_id not in user_data or user_data[chat_id].get('state') != 'photo':
        return

    if len(user_data[chat_id]['photos']) == 0:
        bot.send_message(chat_id, "❌ Вы не отправили ни одного фото. Отправьте хотя бы одно.")
        return
        user_data[chat_id]['state'] = 'text'
    bot.send_message(
        chat_id,
        "✏️ Теперь отправьте текст объявления:",
        reply_markup=telebot.types.ReplyKeyboardRemove()
    )

@bot.message_handler(func=lambda m: user_data.get(m.chat.id, {}).get('state') == 'text')
def handle_text(message):
    chat_id = message.chat.id
    user_data[chat_id]['text'] = message.text
    user_data[chat_id]['state'] = 'confirm'

    preview = (
        f"📋 Предпросмотр объявления:\n\n"
        f"{message.text}\n\n"
        f"📷 Прикреплено фото: {len(user_data[chat_id]['photos'])}"
    )
    bot.send_message(chat_id, preview, reply_markup=confirm_kb())

@bot.message_handler(func=lambda m: m.text == "Готово ☑️")
def confirm_send(message):
    chat_id = message.chat.id
    if chat_id not in user_data or user_data[chat_id].get('state') != 'confirm':
        return

    data = user_data[chat_id]
    bot.send_message(chat_id, "⏳ Отправляю объявления в группы ВК...")

    try:
        report = send_to_vk_groups(data['text'], data['photos'], data['category'])
        bot.send_message(chat_id, f"📋 Отправка завершена!\n\n{report}", reply_markup=main_kb())
    except Exception as e:
        bot.send_message(chat_id, f"🔥 Критическая ошибка: {str(e)}", reply_markup=main_kb())
    finally:
        # Удаляем временные файлы
        for p in data.get('photos', []):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception as e:
                print(f"[Cleanup] Не удалось удалить {p}: {e}")
        # Сбрасываем состояние
        user_data[chat_id] = {'state': 'main'}

@bot.message_handler(func=lambda m: m.text == "Изменить")
def reset_ad(message):
    chat_id = message.chat.id
    # Удаляем ранее сохранённые фото
    if chat_id in user_data:
        for p in user_data[chat_id].get('photos', []):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except:
                pass

    user_data[chat_id] = {'state': 'category', 'photos': [], 'text': '', 'category': None}
    bot.send_message(chat_id, "Выберите категорию групп:", reply_markup=category_kb())

# ─── Flask keep-alive (для хостингов типа Render / Railway) ───

@app.route('/')
def index():
    return "✅ Bot is running", 200

def run_bot():
    reset_webhook()
    print("[Bot] Запуск infinity_polling...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

if name == 'main':
    # Бот работает в отдельном потоке, Flask — в главном
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    app.run(host='0.0.0.0', port=PORT)
