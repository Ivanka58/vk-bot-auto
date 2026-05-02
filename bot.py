import os
import telebot
from telebot import types
from flask import Flask
import threading
from dotenv import load_dotenv
from vk_worker import send_to_vk_groups

load_dotenv()

TOKEN = os.getenv("TG_TOKEN")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Хранилище данных пользователя
user_data = {}

# --- КЛАВИАТУРЫ ---
def get_start_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("Отправить объявление"))
    return kb

def get_category_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("📁 Обычные группы"), types.KeyboardButton("⭐ Крупные группы"))
    return kb

def get_finish_photos_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("Закончить отправку фото ✅"))
    return kb

def get_confirm_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("Готово ☑️"), types.KeyboardButton("Изменить"))
    return kb

# --- ОБРАБОТЧИКИ ---
@bot.message_handler(commands=['start', 'auto'])
def send_welcome(message):
    chat_id = message.chat.id
    user_data[chat_id] = {'step': 'main', 'category': None, 'photos': [], 'text': None}
    bot.send_message(chat_id, "Привет! Чтобы отправить объявление в ВК, нажмите на кнопку ниже 👇", reply_markup=get_start_kb())

@bot.message_handler(func=lambda m: m.text == "Отправить объявление")
def ask_category(message):
    chat_id = message.chat.id
    user_data[chat_id] = {'step': 'category', 'category': None, 'photos': [], 'text': None}
    bot.send_message(chat_id, "Выберите категорию групп:", reply_markup=get_category_kb())

@bot.message_handler(func=lambda m: m.text in ["📁 Обычные группы", "⭐ Крупные группы"])
def category_chosen(message):
    chat_id = message.chat.id
    category = 'usual' if message.text == "📁 Обычные группы" else 'large'
    user_data[chat_id]['step'] = 'photo'
    user_data[chat_id]['category'] = category
    bot.send_message(chat_id, "Отправьте фотографии вашего объявления (до 10 шт.)", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(content_types=['photo'])
def handle_photos(message):
    chat_id = message.chat.id
    if chat_id not in user_data or user_data[chat_id].get('step') != 'photo':
        return
    if len(user_data[chat_id]['photos']) < 10:
        file_id = message.photo[-1].file_id
        user_data[chat_id]['photos'].append(file_id)
        msg = f"Фото получено ({len(user_data[chat_id]['photos'])}/10). Можете отправить еще или нажмите кнопку."
        bot.send_message(chat_id, msg, reply_markup=get_finish_photos_kb())
    else:
        bot.send_message(chat_id, "Достигнут лимит 10 фото. Нажмите кнопку.", reply_markup=get_finish_photos_kb())

@bot.message_handler(func=lambda m: m.text == "Закончить отправку фото ✅")
def finish_photos_step(message):
    chat_id = message.chat.id
    if chat_id not in user_data or not user_data[chat_id]['photos']:
        bot.send_message(chat_id, "Вы не отправили ни одного фото!")
        return
    user_data[chat_id]['step'] = 'text'
    bot.send_message(chat_id, "Теперь отправьте текст к вашему объявлению", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: True)
def get_text(message):
    chat_id = message.chat.id
    if chat_id not in user_data or user_data[chat_id].get('step') != 'text':
        return
    user_data[chat_id]['text'] = message.text
    bot.send_message(chat_id, "Объявление готово! Подтверждаете?", reply_markup=get_confirm_kb())
    user_data[chat_id]['step'] = 'confirm'

@bot.message_handler(func=lambda m: m.text in ["Готово ☑️", "Изменить"])
def confirm_step(message):
    chat_id = message.chat.id
    if chat_id not in user_data:
        return
    if message.text == "Изменить":
        ask_category(message)
        return

    bot.send_message(chat_id, "Начинаю публикацию в выбранную категорию...")
    data = user_data[chat_id]
    paths = []
    try:
        # Скачиваем фото
        for i, photo_id in enumerate(data['photos']):
            file_info = bot.get_file(photo_id)
            downloaded = bot.download_file(file_info.file_path)
            path = f"temp_{chat_id}_{i}.jpg"
            with open(path, 'wb') as f:
                f.write(downloaded)
            paths.append(path)
        # Отправляем через VK worker
        report = send_to_vk_groups(data['text'], paths, data['category'])
        bot.send_message(chat_id, report, reply_markup=get_start_kb())
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка: {e}", reply_markup=get_start_kb())
    finally:
        for p in paths:
            if os.path.exists(p):
                os.remove(p)
        user_data[chat_id] = {'step': 'main', 'category': None, 'photos': [], 'text': None}

# --- ЗАПУСК ---
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    bot.infinity_polling()
