import os
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import requests
import threading
from flask import Flask
from vk_worker import send_to_vk_groups
from dotenv import load_dotenv

load_dotenv()

TG_TOKEN = os.getenv('TG_TOKEN')

# --- ПОРТ ДЛЯ AMVERA: если в env null/пусто — ставим 80 ---
raw_port = os.getenv('PORT')
try:
    PORT = int(raw_port) if raw_port and raw_port.lower() not in ('null', '', 'none') else 80
except ValueError:
    PORT = 80
# ---------------------------------------------------------

bot = telebot.TeleBot(TG_TOKEN)
app = Flask(__name__)

# Хранилище состояний
user_data = {}

# ─── Вспомогательные функции ───

def reset_webhook():
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

def safe_send(chat_id, text, reply_markup=None):
    """Безопасная отправка сообщения с логированием ошибок."""
    try:
        bot.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception as e:
        print(f"[safe_send] Ошибка отправки в {chat_id}: {e}")

# ─── Обработчики ───

@bot.message_handler(commands=['start'])
def cmd_start(message):
    try:
        chat_id = message.chat.id
        user_data[chat_id] = {'state': 'main'}
        print(f"[START] Пользователь {chat_id}")
        bot.send_message(
            chat_id,
            "👋 Привет! Я бот для публикации объявлений в группы ВКонтакте.\n\n"
            "Нажмите кнопку ниже, чтобы начать.",
            reply_markup=main_kb()
        )
    except Exception as e:
        print(f"[START ERROR] {e}")

@bot.message_handler(func=lambda m: m.text == "Отправить объявление")
def send_ad(message):
    try:
        chat_id = message.chat.id
        user_data[chat_id] = {'state': 'category', 'photos': [], 'text': '', 'category': None}
        print(f"[SEND_AD] Пользователь {chat_id} начал создание объявления")
        bot.send_message(chat_id, "Выберите категорию групп:", reply_markup=category_kb())
    except Exception as e:
        print(f"[SEND_AD ERROR] {e}")

@bot.message_handler(func=lambda m: m.text in ["📁 Обычные группы", "⭐ Крупные группы"])
def choose_category(message):
    try:
        chat_id = message.chat.id
        if chat_id not in user_data or user_data[chat_id].get('state') != 'category':
            return

        category = 'usual' if 'Обычные' in message.text else 'large'
        user_data[chat_id]['category'] = category
        user_data[chat_id]['state'] = 'photo'

        print(f"[CATEGORY] Пользователь {chat_id} выбрал {category}")
        bot.send_message(
            chat_id,
            "📷 Отправьте фото (до 10 шт.).\nКогда закончите — нажмите кнопку ниже.",
            reply_markup=photo_kb()
        )
    except Exception as e:
        print(f"[CATEGORY ERROR] {e}")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        chat_id = message.chat.id
        if chat_id not in user_data or user_data[chat_id].get('state') != 'photo':
            return

        photos = user_data[chat_id]['photos']
        if len(photos) >= 10:
            bot.send_message(chat_id, "❌ Достигнут лимит в 10 фото. Нажмите «Закончить отправку фото ✅»")
            return

        # Берём фото максимального качества
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        temp_dir = f"temp/{chat_id}"
        os.makedirs(temp_dir, exist_ok=True)

        file_path = os.path.join(temp_dir, f"photo_{len(photos)}.jpg")
        with open(file_path, 'wb') as f:
            f.write(downloaded_file)

        photos.append(file_path)
        user_data[chat_id]['photos'] = photos

        print(f"[PHOTO] Пользователь {chat_id} отправил фото {len(photos)}/10")
        bot.send_message(
            chat_id,
            f"📷 Фото {len(photos)}/10 получено. Можете отправить ещё или нажать «Закончить отправку фото ✅»",
            reply_markup=photo_kb()
        )
    except Exception as e:
        print(f"[PHOTO ERROR] {e}")
        safe_send(message.chat.id, f"🔥 Ошибка при сохранении фото: {e}")

@bot.message_handler(func=lambda m: m.text == "Закончить отправку фото ✅")
def finish_photos(message):
    try:
        chat_id = message.chat.id
        if chat_id not in user_data or user_data[chat_id].get('state') != 'photo':
            return

        if len(user_data[chat_id]['photos']) == 0:
            bot.send_message(chat_id, "❌ Вы не отправили ни одного фото. Отправьте хотя бы одно.")
            return

        user_data[chat_id]['state'] = 'text'
        print(f"[FINISH_PHOTOS] Пользователь {chat_id} закончил отправку фото")
        bot.send_message(
            chat_id,
            "✏️ Теперь отправьте текст объявления:",
            reply_markup=ReplyKeyboardRemove()
        )
    except Exception as e:
        print(f"[FINISH_PHOTOS ERROR] {e}")
        safe_send(chat_id, f"🔥 Ошибка: {e}")

@bot.message_handler(func=lambda m: user_data.get(m.chat.id, {}).get('state') == 'text')
def handle_text(message):
    try:
        chat_id = message.chat.id
        user_text = message.text

        print(f"[TEXT] Пользователь {chat_id} отправил текст: {user_text[:50]}...")
        user_data[chat_id]['text'] = user_text
        user_data[chat_id]['state'] = 'confirm'

        preview = (
            f"📋 Предпросмотр объявления:\n\n"
            f"{user_text}\n\n"
            f"📷 Прикреплено фото: {len(user_data[chat_id]['photos'])}"
        )
        bot.send_message(chat_id, preview, reply_markup=confirm_kb())
    except Exception as e:
        print(f"[TEXT ERROR] {e}")
        safe_send(chat_id, f"🔥 Ошибка при обработке текста: {e}")

@bot.message_handler(func=lambda m: m.text == "Готово ☑️")
def confirm_send(message):
    try:
        chat_id = message.chat.id
        if chat_id not in user_data or user_data[chat_id].get('state') != 'confirm':
            return

        data = user_data[chat_id]
        print(f"[CONFIRM] Пользователь {chat_id} подтвердил отправку")
        bot.send_message(chat_id, "⏳ Отправляю объявления в группы ВК...")

        try:
            report = send_to_vk_groups(data['text'], data['photos'], data['category'])
            bot.send_message(chat_id, f"📋 Отправка завершена!\n\n{report}", reply_markup=main_kb())
        except Exception as e:
            err_msg = str(e)
            print(f"[VK ERROR] {err_msg}")
            bot.send_message(chat_id, f"🔥 Критическая ошибка при отправке в ВК:\n{err_msg}", reply_markup=main_kb())
        finally:
            # Удаляем временные файлы
            for p in data.get('photos', []):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                        print(f"[CLEANUP] Удалён файл: {p}")
                except Exception as e:
                    print(f"[CLEANUP ERROR] {e}")
            # Сбрасываем состояние
            user_data[chat_id] = {'state': 'main'}
    except Exception as e:
        print(f"[CONFIRM ERROR] {e}")
        safe_send(message.chat.id, f"🔥 Внутренняя ошибка: {e}")

@bot.message_handler(func=lambda m: m.text == "Изменить")
def reset_ad(message):
    try:
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
        print(f"[RESET] Пользователь {chat_id} сбросил объявление")
        bot.send_message(chat_id, "Выберите категорию групп:", reply_markup=category_kb())
    except Exception as e:
        print(f"[RESET ERROR] {e}")

# ─── Fallback: если сообщение не попало ни в один хендлер ───
@bot.message_handler(func=lambda m: True)
def fallback(message):
    chat_id = message.chat.id
    state = user_data.get(chat_id, {}).get('state', 'unknown')
    print(f"[FALLBACK] Пользователь {chat_id}, состояние '{state}', текст: {message.text}")
    bot.send_message(
        chat_id,
        "❓ Я не понял команду. Если что-то пошло не так — нажмите /start",
        reply_markup=main_kb()
    )

# ─── Flask keep-alive ───

@app.route('/')
def index():
    return "✅ Bot is running", 200

def run_bot():
    reset_webhook()
    print(f"[Bot] Запуск infinity_polling... (PORT={PORT})")
    # УБРАН non_stop=True — в этой версии библиотеки он уже внутри infinity_polling
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

if __name__ == '__main__':
    print(f"[Server] Запуск Flask на 0.0.0.0:{PORT}")
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    app.run(host='0.0.0.0', port=PORT)