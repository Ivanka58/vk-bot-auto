import os
import time
import json
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id
from flask import Flask
import threading

# === ЗАГРУЗКА ПЕРЕМЕННЫХ ===
VK_TOKEN = os.getenv("VK_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")
GROUPS_USUAL = [int(gid.strip()) for gid in os.getenv("GROUPS_USUAL", "").split(",") if gid.strip()]
GROUPS_LARGE = [int(gid.strip()) for gid in os.getenv("GROUPS_LARGE", "").split(",") if gid.strip()]

if not VK_TOKEN or not GROUP_ID:
    raise ValueError("❌ Ошибка: VK_TOKEN или GROUP_ID не заданы")

# === ИНИЦИАЛИЗАЦИЯ VK ===
vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()
upload = vk_api.VkUpload(vk_session)

# === ХРАНИЛИЩЕ ДАННЫХ ПОЛЬЗОВАТЕЛЕЙ ===
user_data = {}

# === FLASK ДЛЯ ПИНГА НА RENDER ===
app = Flask(__name__)

@app.route('/')
def health():
    return "Bot is alive", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# === КЛАВИАТУРЫ ===
def main_menu_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button('📤 Отправить объявление', color=VkKeyboardColor.POSITIVE)
    return keyboard

def category_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('📁 Обычные группы', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('⭐ Крупные группы', color=VkKeyboardColor.PRIMARY)
    return keyboard

def finish_photos_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('✅ Закончить отправку фото', color=VkKeyboardColor.POSITIVE)
    return keyboard

def confirm_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('✅ Готово', color=VkKeyboardColor.POSITIVE)
    keyboard.add_button('✏️ Изменить', color=VkKeyboardColor.SECONDARY)
    return keyboard

# === ОТПРАВКА СООБЩЕНИЙ С КЛАВИАТУРОЙ ===
def send_msg(user_id, text, keyboard=None):
    vk.messages.send(
        user_id=user_id,
        message=text,
        random_id=get_random_id(),
        keyboard=keyboard.get_keyboard() if keyboard else None
    )

# === ЗАГРУЗКА ФОТО НА СЕРВЕР ВК ===
def upload_photos(photos_data):
    """photos_data — список словарей с ключами: type (photo_id или url) и data"""
    attachments = []
    for photo in photos_data:
        if photo['type'] == 'url':
            # Скачать по URL и загрузить
            import requests
            img = requests.get(photo['data']).content
            photo_upload = upload.photo_messages(img)[0]
        elif photo['type'] == 'file':
            # Загрузить файл с диска
            photo_upload = upload.photo_messages(photo['data'])[0]
        else:
            continue
        attachments.append(f"photo{photo_upload['owner_id']}_{photo_upload['id']}")
    return attachments

# === ПУБЛИКАЦИЯ ПОСТА В ГРУППУ ===
def post_to_group(group_id, text, attachments):
    try:
        vk.wall.post(
            owner_id=group_id,
            message=text,
            attachments=','.join(attachments),
            signed=False
        )
        return f"✅ Группа {group_id}: отправлено"
    except Exception as e:
        return f"❌ Группа {group_id}: ошибка — {str(e)[:80]}"

# === ГЛАВНЫЙ ЦИКЛ БОТА ===
def main():
    longpoll = VkBotLongPoll(vk_session, GROUP_ID)
    send_msg(GROUP_ID, "✅ Бот запущен", main_menu_keyboard())

    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW and event.obj.message['text']:
            user_id = event.obj.message['from_id']
            text = event.obj.message['text'].strip()

            # Инициализация пользователя
            if user_id not in user_data:
                user_data[user_id] = {'step': 'main', 'category': None, 'photos': [], 'text': None}

            state = user_data[user_id]

            # === ОБРАБОТКА КОМАНДЫ /start ===
            if text == '/start':
                state['step'] = 'main'
                state['category'] = None
                state['photos'] = []
                state['text'] = None
                send_msg(user_id, "Привет! Нажми кнопку ниже, чтобы отправить объявление 👇", main_menu_keyboard())
                continue

            # === КНОПКА "ОТПРАВИТЬ ОБЪЯВЛЕНИЕ" ===
            if text == '📤 Отправить объявление' and state['step'] == 'main':
                state['step'] = 'select_category'
                send_msg(user_id, "Выберите категорию групп:", category_keyboard())
                continue

            # === ВЫБОР КАТЕГОРИИ ===
            if text in ['📁 Обычные группы', '⭐ Крупные группы'] and state['step'] == 'select_category':
                if text == '📁 Обычные группы':
                    state['category'] = 'usual'
                else:
                    state['category'] = 'large'
                state['step'] = 'wait_photos'
                send_msg(user_id, "Отправьте фото (до 10 шт.)", finish_photos_keyboard())
                continue

            # === ОБРАБОТКА ФОТО ===
            if state['step'] == 'wait_photos' and event.obj.message.get('attachments'):
                new_photos = []
                for att in event.obj.message['attachments']:
                    if att['type'] == 'photo':
                        sizes = att['photo']['sizes']
                        max_size = max(sizes, key=lambda x: x['height'] * x['width'])
                        new_photos.append({'type': 'url', 'data': max_size['url']})
                if len(state['photos']) + len(new_photos) > 10:
                    send_msg(user_id, f"❌ Лимит фото 10! У вас уже {len(state['photos'])}. Отправьте меньше.")
                else:
                    state['photos'].extend(new_photos)
                    send_msg(user_id, f"📸 Фото получено ({len(state['photos'])}/10)", finish_photos_keyboard())
                continue

            # === КНОПКА "ЗАКОНЧИТЬ ОТПРАВКУ ФОТО" ===
            if text == '✅ Закончить отправку фото' and state['step'] == 'wait_photos':
                if not state['photos']:
                    send_msg(user_id, "❌ Вы не отправили ни одного фото! Отправьте хотя бы одно.")
                else:
                    state['step'] = 'wait_text'
                    send_msg(user_id, "✍️ Теперь отправьте текст к объявлению")
                continue

            # === ПОЛУЧЕНИЕ ТЕКСТА ===
            if state['step'] == 'wait_text' and text:
                state['text'] = text
                state['step'] = 'confirm'
                send_msg(user_id, f"✅ Объявление готово!\n\nТекст: {text[:100]}...", confirm_keyboard())
                continue

            # === КНОПКИ "ГОТОВО" / "ИЗМЕНИТЬ" ===
            if state['step'] == 'confirm':
                if text == '✅ Готово':
                    groups = GROUPS_USUAL if state['category'] == 'usual' else GROUPS_LARGE
                    if not groups:
                        send_msg(user_id, "❌ Нет групп для этой категории.")
                        continue

                    send_msg(user_id, f"🚀 Начинаю отправку в {len(groups)} групп. Подождите...")

                    attachments = await_upload_photos(state['photos'])

                    results = []
                    for gid in groups:
                        res = post_to_group(gid, state['text'], attachments)
                        results.append(res)
                        time.sleep(1)

                    report = "\n".join(results)
                    send_msg(user_id, f"📋 Отправка завершена!\n{report}", main_menu_keyboard())

                    # Сброс состояния
                    state['step'] = 'main'
                    state['category'] = None
                    state['photos'] = []
                    state['text'] = None

                elif text == '✏️ Изменить':
                    state['step'] = 'select_category'
                    state['category'] = None
                    state['photos'] = []
                    state['text'] = None
                    send_msg(user_id, "🔄 Начинаем заново. Выберите категорию:", category_keyboard())
                continue

            # === ЕСЛИ НИ ОДИН ПУНКТ НЕ ПОДОШЁЛ ===
            send_msg(user_id, "❓ Неизвестная команда. Нажмите /start или используйте кнопки.")

def await_upload_photos(photos_data):
    """Функция-заглушка для загрузки фото. В реальности нужно получать файлы или ссылки."""
    attachments = []
    for photo in photos_data:
        # Временно генерируем тестовое вложение
        attachments.append(f"photo{photo['owner_id']}_{photo['id']}")
    return attachments

# === ЗАПУСК ===
if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    main()
