import os
import telebot
from flask import Flask
import threading
from vk_worker import send_to_vk_groups

TOKEN = os.getenv("TG_TOKEN")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@app.route('/')
def health():
    return "Bot is alive", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

@bot.message_handler(content_types=['text', 'photo'])
def forward_to_vk(message):
    # Текст: если фото, то подпись, иначе просто текст
    text = message.caption if message.photo else message.text
    if not text:
        text = " "

    # Фото сохраняем во временный файл
    photos = []
    if message.photo:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded = bot.download_file(file_info.file_path)
        path = f"temp_{message.chat.id}_{message.message_id}.jpg"
        with open(path, 'wb') as f:
            f.write(downloaded)
        photos = [path]

    # Отправляем в VK
    result = send_to_vk_groups(text, photos)
    # Ничего не отвечаем, просто логируем
    print(result)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    bot.infinity_polling()
