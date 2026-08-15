import os
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)
import requests
import threading
from flask import Flask
from vk_worker import send_to_vk_groups
from dotenv import load_dotenv
import time
from datetime import datetime
from db_worker import (
    init_db, save_scheduled_ad, get_scheduled_ads, get_scheduled_ad_by_id,
    delete_scheduled_ad, update_scheduled_ad, check_time_conflict
)

load_dotenv()

TG_TOKEN = os.getenv('TG_TOKEN')

raw_port = os.getenv('PORT')
try:
    PORT = int(raw_port) if raw_port and raw_port.lower() not in ('null', '', 'none') else 80
except ValueError:
    PORT = 80

bot = telebot.TeleBot(TG_TOKEN)
app = Flask(__name__)

user_data = {}

# Папка для постоянного хранения фото (Amvera persistenceMount: /data)
PHOTO_STORAGE = "/data/scheduled_photos"
os.makedirs(PHOTO_STORAGE, exist_ok=True)

# Инициализация БД
init_db()

# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

def reset_webhook():
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/setWebhook?url="
        r = requests.get(url, timeout=10)
        print(f"[Webhook] Сброшен: {r.status_code}")
    except Exception as e:
        print(f"[Webhook] Ошибка: {e}")

def main_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📤 Отправить объявление"))
    kb.add(KeyboardButton("📅 Запланировать отправку"), KeyboardButton("📋 Запланированные"))
    return kb

def back_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("◀️ Назад"))
    return kb

def category_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📁 Обычные группы"), KeyboardButton("⭐ Крупные группы"))
    kb.add(KeyboardButton("◀️ Назад"))
    return kb

def photo_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("✅ Закончить отправку фото"))
    kb.add(KeyboardButton("◀️ Назад"))
    return kb

def confirm_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("☑️ Готово"), KeyboardButton("🔄 Изменить"))
    kb.add(KeyboardButton("◀️ Назад"))
    return kb

def account_inline_kb():
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("Аксессуары", callback_data='acc_accessories'),
        InlineKeyboardButton("Дианы", callback_data='acc_autosale')
    )
    return kb

def days_inline_kb(selected_days=None):
    if selected_days is None:
        selected_days = []
    kb = InlineKeyboardMarkup()
    days = [
        ('Пн', 'mon'), ('Вт', 'tue'), ('Ср', 'wed'), ('Чт', 'thu'),
        ('Пт', 'fri'), ('Сб', 'sat'), ('Вс', 'sun')
    ]

    row = []
    for name, code in days:
        if code in selected_days:
            row.append(InlineKeyboardButton(f"✅ {name}", callback_data=f'day_{code}'))
        else:
            row.append(InlineKeyboardButton(name, callback_data=f'day_{code}'))
    kb.row(*row)

    if selected_days:
        kb.add(InlineKeyboardButton("✅ Закончить выбор", callback_data='days_finish'))
    return kb

def scheduled_detail_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📝 Изменить объявление"))
    kb.add(KeyboardButton("👤 Изменить аккаунт"))
    kb.add(KeyboardButton("📁 Изменить группы"))
    kb.add(KeyboardButton("📅 Изменить дни публикации"))
    kb.add(KeyboardButton("⏰ Изменить время публикации"))
    kb.add(KeyboardButton("🗑 Удалить объявление"))
    kb.add(KeyboardButton("◀️ Назад"))
    return kb

def scheduled_list_kb(ads):
    kb = InlineKeyboardMarkup()
    day_names = {'mon': 'пн', 'tue': 'вт', 'wed': 'ср', 'thu': 'чт', 'fri': 'пт', 'sat': 'сб', 'sun': 'вс'}
    for ad in ads:
        days_str = ', '.join([day_names.get(d, d) for d in ad['days']])
        label = f"{days_str} — {ad['time']}"
        kb.add(InlineKeyboardButton(label, callback_data=f'sched_{ad["id"]}'))
    return kb

def format_days(days):
    day_names = {
        'mon': 'понедельник', 'tue': 'вторник', 'wed': 'среда', 'thu': 'четверг',
        'fri': 'пятница', 'sat': 'суббота', 'sun': 'воскресенье'
    }
    order = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    result = []
    for d in order:
        if d in days:
            result.append(day_names[d])
    return ', '.join(result)

def format_days_short(days):
    day_names = {
        'mon': 'пн', 'tue': 'вт', 'wed': 'ср', 'thu': 'чт',
        'fri': 'пт', 'sat': 'сб', 'sun': 'вс'
    }
    order = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    result = []
    for d in order:
        if d in days:
            result.append(day_names[d])
    return ', '.join(result)

def get_user_state(chat_id):
    return user_data.get(chat_id, {}).get('state', 'main')

def set_user_state(chat_id, state):
    if chat_id not in user_data:
        user_data[chat_id] = {}
    user_data[chat_id]['state'] = state

def get_user_data(chat_id):
    return user_data.get(chat_id, {})

def init_user_data(chat_id, mode='instant'):
    user_data[chat_id] = {
        'state': 'account',
        'photos': [],
        'text': '',
        'category': None,
        'account': None,
        'mode': mode,
        'days': [],
        'time': None,
        'viewing_ad_id': None,
        'editing_ad_id': None,
        'temp_days': []
    }

def save_photo_persistent(chat_id, file_data, filename):
    """Сохраняет фото в постоянное хранилище /data"""
    user_dir = os.path.join(PHOTO_STORAGE, str(chat_id))
    os.makedirs(user_dir, exist_ok=True)
    path = os.path.join(user_dir, filename)
    with open(path, 'wb') as f:
        f.write(file_data)
    return path

def send_photos_as_album(chat_id, photo_paths, caption=None):
    """Отправляет фото альбомом (одним сообщением)"""
    if not photo_paths:
        return

    valid_photos = [p for p in photo_paths if os.path.exists(p)]
    if not valid_photos:
        return

    media = []
    for i, path in enumerate(valid_photos[:10]):
        with open(path, 'rb') as f:
            photo_data = f.read()
        if i == 0 and caption:
            media.append(InputMediaPhoto(photo_data, caption=caption, parse_mode='HTML'))
        else:
            media.append(InputMediaPhoto(photo_data))

    if media:
        bot.send_media_group(chat_id, media)

# ============ ОБЩИЕ ОБРАБОТЧИКИ ============

@bot.message_handler(commands=['start'])
def cmd_start(message):
    chat_id = message.chat.id
    user_data[chat_id] = {'state': 'main'}
    bot.send_message(chat_id, "👋 Привет! Выберите действие:", reply_markup=main_kb())

# ============ ОБЫЧНАЯ ОТПРАВКА ============

@bot.message_handler(func=lambda m: m.text == "📤 Отправить объявление")
def send_ad(message):
    chat_id = message.chat.id
    init_user_data(chat_id, mode='instant')
    bot.send_message(
        chat_id,
        "📤 Отправить объявление\n\nЧерез какой аккаунт отправляем?",
        reply_markup=account_inline_kb()
    )

# ============ ЗАПЛАНИРОВАННАЯ ОТПРАВКА (сразу создание) ============

@bot.message_handler(func=lambda m: m.text == "📅 Запланировать отправку")
def schedule_ad_start(message):
    chat_id = message.chat.id
    init_user_data(chat_id, mode='schedule')
    bot.send_message(
        chat_id,
        "📅 Запланировать отправку\n\nЧерез какой аккаунт отправляем?",
        reply_markup=account_inline_kb()
    )

# ============ СПИСОК ЗАПЛАНИРОВАННЫХ ============

@bot.message_handler(func=lambda m: m.text == "📋 Запланированные")
def show_scheduled(message):
    chat_id = message.chat.id
    set_user_state(chat_id, 'scheduled_list')
    show_scheduled_list(chat_id)

def show_scheduled_list(chat_id):
    ads = get_scheduled_ads(chat_id)
    if not ads:
        bot.send_message(chat_id, "📭 У вас пока нет запланированных объявлений.", reply_markup=main_kb())
        set_user_state(chat_id, 'main')
        return

    msg = "📅 Ваши запланированные объявления:"
    kb = scheduled_list_kb(ads)
    bot.send_message(chat_id, msg, reply_markup=kb)

# ============ ВЫБОР АККАУНТА ============

@bot.callback_query_handler(func=lambda call: call.data.startswith('acc_'))
def choose_account(call):
    chat_id = call.message.chat.id
    state = get_user_state(chat_id)

    if state not in ['account', 'edit_account']:
        bot.answer_callback_query(call.id, "❌ Это действие больше не актуально")
        return

    account = 'accessories' if call.data == 'acc_accessories' else 'autosale'
    name = "Аксессуары" if account == 'accessories' else "Дианы"
    data = get_user_data(chat_id)

    if state == 'edit_account':
        ad_id = data.get('editing_ad_id')
        if ad_id:
            update_scheduled_ad(ad_id, {'account': account})
            bot.edit_message_text(
                f"✅ Аккаунт изменён на: <b>{name}</b>",
                chat_id=chat_id,
                message_id=call.message.message_id,
                parse_mode='HTML'
            )
            bot.answer_callback_query(call.id, f"Выбран: {name}")
            set_user_state(chat_id, 'main')
            show_scheduled_list(chat_id)
        return

    user_data[chat_id]['account'] = account
    user_data[chat_id]['state'] = 'category'

    print(f"[ACCOUNT] Пользователь {chat_id} выбрал: {name}")
    bot.answer_callback_query(call.id, f"Выбран: {name}")
    bot.edit_message_text(
        f"✅ Аккаунт: <b>{name}</b>\n\nТеперь выбери категорию групп:",
        chat_id=chat_id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    bot.send_message(chat_id, "Выбери категорию:", reply_markup=category_kb())

# ============ ВЫБОР КАТЕГОРИИ ============

@bot.message_handler(func=lambda m: m.text in ["📁 Обычные группы", "⭐ Крупные группы"])
def choose_category(message):
    chat_id = message.chat.id
    state = get_user_state(chat_id)

    if state not in ['category', 'edit_groups']:
        return

    category = 'usual' if 'Обычные' in message.text else 'large'
    data = get_user_data(chat_id)

    if state == 'edit_groups':
        ad_id = data.get('editing_ad_id')
        if ad_id:
            update_scheduled_ad(ad_id, {'category': category})
            cat_name = "Обычные" if category == 'usual' else "Крупные"
            bot.send_message(chat_id, f"✅ Группы изменены на: {cat_name}", reply_markup=main_kb())
            set_user_state(chat_id, 'main')
            show_scheduled_list(chat_id)
        return

    user_data[chat_id]['category'] = category
    user_data[chat_id]['state'] = 'photo'

    print(f"[CATEGORY] Пользователь {chat_id} выбрал {category}")
    bot.send_message(
        chat_id,
        "📷 Отправь фото (до 10 шт.). Когда закончишь — нажми кнопку ниже.",
        reply_markup=photo_kb()
    )

# ============ ФОТО ============

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id
    state = get_user_state(chat_id)

    if state != 'photo':
        return

    photos = user_data[chat_id]['photos']
    if len(photos) >= 10:
        return bot.send_message(chat_id, "❌ Лимит 10 фото. Нажми «✅ Закончить отправку фото»")

    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded = bot.download_file(file_info.file_path)

    # Сохраняем в постоянное хранилище /data
    filename = f"photo_{chat_id}_{int(datetime.now().timestamp())}_{len(photos)}.jpg"
    path = save_photo_persistent(chat_id, downloaded, filename)

    photos.append(path)
    print(f"[PHOTO] Сохранено: {path} | Размер: {os.path.getsize(path)} байт")
    bot.send_message(
        chat_id,
        f"📷 Фото {len(photos)}/10. Можешь ещё или нажать «✅ Закончить отправку фото»",
        reply_markup=photo_kb()
    )

@bot.message_handler(func=lambda m: m.text == "✅ Закончить отправку фото")
def finish_photos(message):
    chat_id = message.chat.id
    state = get_user_state(chat_id)

    if state != 'photo':
        return
    if not user_data[chat_id]['photos']:
        return bot.send_message(chat_id, "❌ Ни одного фото. Отправь хотя бы одно.")

    user_data[chat_id]['state'] = 'text'
    print(f"[FINISH PHOTOS] Файлы: {user_data[chat_id]['photos']}")
    from telebot.types import ReplyKeyboardRemove
    bot.send_message(chat_id, "✏️ Теперь отправь текст объявления:", reply_markup=ReplyKeyboardRemove())

# ============ ТЕКСТ ============

@bot.message_handler(func=lambda m: get_user_state(m.chat.id) == 'text')
def handle_text(message):
    chat_id = message.chat.id
    data = get_user_data(chat_id)

    user_data[chat_id]['text'] = message.text

    if data.get('mode') == 'schedule':
        user_data[chat_id]['state'] = 'days'
        user_data[chat_id]['days'] = []
        bot.send_message(
            chat_id,
            "📅 Выберите дни недели для отправки:",
            reply_markup=days_inline_kb([])
        )
    else:
        user_data[chat_id]['state'] = 'confirm'
        account = data.get('account', 'accessories')
        acc_name = "Аксессуары" if account == 'accessories' else "Дианы"
        preview = (
            f"📋 Предпросмотр:\n\n"
            f"{message.text}\n\n"
            f"📷 Фото: {len(data['photos'])}\n"
            f"👤 Аккаунт: {acc_name}"
        )
        bot.send_message(chat_id, preview, reply_markup=confirm_kb())

# ============ ВЫБОР ДНЕЙ НЕДЕЛИ ============

@bot.callback_query_handler(func=lambda call: call.data.startswith('day_'))
def choose_day(call):
    chat_id = call.message.chat.id
    state = get_user_state(chat_id)

    if state not in ['days', 'edit_days']:
        bot.answer_callback_query(call.id, "❌ Это действие больше не актуально")
        return

    day_code = call.data.replace('day_', '')
    data = get_user_data(chat_id)

    if state == 'edit_days':
        days = data.get('temp_days', [])
    else:
        days = data.get('days', [])

    if day_code in days:
        days.remove(day_code)
    else:
        days.append(day_code)

    if state == 'edit_days':
        user_data[chat_id]['temp_days'] = days
    else:
        user_data[chat_id]['days'] = days

    days_str = format_days(days)

    if days:
        msg = f"Выбрано: {days_str}\n\nВыбрать ещё?"
    else:
        msg = "Выберите дни недели:"

    bot.edit_message_text(
        msg,
        chat_id=chat_id,
        message_id=call.message.message_id,
        reply_markup=days_inline_kb(days)
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'days_finish')
def finish_days(call):
    chat_id = call.message.chat.id
    state = get_user_state(chat_id)

    if state not in ['days', 'edit_days']:
        bot.answer_callback_query(call.id, "❌ Это действие больше не актуально")
        return

    data = get_user_data(chat_id)

    if state == 'edit_days':
        days = data.get('temp_days', [])
        if not days:
            bot.answer_callback_query(call.id, "❌ Выберите хотя бы один день!")
            return

        ad_id = data.get('editing_ad_id')
        ad = get_scheduled_ad_by_id(ad_id)

        if ad and check_time_conflict(chat_id, days, ad['time'], exclude_id=ad_id):
            bot.answer_callback_query(call.id, "❌ Конфликт времени!")
            bot.send_message(chat_id, "❌ Эти дни и время уже заняты другим объявлением. Выберите другие дни.")
            return

        update_scheduled_ad(ad_id, {'days': days})
        days_str = format_days(days)
        bot.edit_message_text(
            f"✅ Дни изменены на: {days_str}",
            chat_id=chat_id,
            message_id=call.message.message_id
        )
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "✅ Дни публикации обновлены", reply_markup=main_kb())
        set_user_state(chat_id, 'main')
        show_scheduled_list(chat_id)
        return

    days = data.get('days', [])
    if not days:
        bot.answer_callback_query(call.id, "❌ Выберите хотя бы один день!")
        return

    days_str = format_days(days)
    user_data[chat_id]['state'] = 'time'

    bot.edit_message_text(
        f"✅ Выбраны дни недели: {days_str}\n\nТеперь напишите время публикации (формат 16:00):",
        chat_id=chat_id,
        message_id=call.message.message_id
    )
    bot.send_message(chat_id, "Введите время:", reply_markup=back_kb())
    bot.answer_callback_query(call.id)

# ============ ВВОД ВРЕМЕНИ ============

@bot.message_handler(func=lambda m: get_user_state(m.chat.id) == 'time')
def handle_time(message):
    chat_id = message.chat.id
    time_str = message.text.strip()
    data = get_user_data(chat_id)

    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        bot.send_message(chat_id, "❌ Неверный формат. Введите время как 16:00", reply_markup=back_kb())
        return

    days = data.get('days', [])
    if check_time_conflict(chat_id, days, time_str):
        bot.send_message(
            chat_id,
            "❌ К сожалению, это время уже занято. Выберите другое время:",
            reply_markup=back_kb()
        )
        return

    user_data[chat_id]['time'] = time_str
    user_data[chat_id]['state'] = 'schedule_confirm'

    account = data.get('account', 'accessories')
    acc_name = "Аксессуары" if account == 'accessories' else "Дианы"
    category_name = "Обычные" if data['category'] == 'usual' else "Крупные"
    days_str = format_days(data['days'])

    caption = (
        f"{data['text']}\n\n"
        f"📋 Публикация объявления\n"
        f"👤 Аккаунт: {acc_name}\n"
        f"📁 Группы: {category_name}\n"
        f"📅 Дни: {days_str}\n"
        f"⏰ Время: {time_str}\n\n"
        f"Всё готово?"
    )

    send_photos_as_album(chat_id, data['photos'], caption=caption)

    if not data['photos']:
        bot.send_message(chat_id, caption, parse_mode='HTML', reply_markup=confirm_kb())
    else:
        bot.send_message(chat_id, "☑️ Подтвердите публикацию:", reply_markup=confirm_kb())

# ============ ПОДТВЕРЖДЕНИЕ ОТПРАВКИ / ПЛАНИРОВАНИЯ ============

@bot.message_handler(func=lambda m: m.text == "☑️ Готово")
def confirm_send(message):
    chat_id = message.chat.id
    state = get_user_state(chat_id)

    if state not in ['confirm', 'schedule_confirm']:
        return

    data = get_user_data(chat_id)

    # === РЕЖИМ ПЛАНИРОВАНИЯ ===
    if state == 'schedule_confirm':
        save_scheduled_ad(
            chat_id=chat_id,
            text=data['text'],
            photos=data['photos'],
            category=data['category'],
            account=data['account'],
            days=data['days'],
            time=data['time']
        )

        days_str = format_days(data['days'])
        bot.send_message(
            chat_id,
            f"✅ Объявление запланировано!\n\n"
            f"📅 Дни: {days_str}\n"
            f"⏰ Время: {data['time']}\n\n"
            f"Я буду отправлять его автоматически.",
            reply_markup=main_kb()
        )

        user_data[chat_id] = {'state': 'main'}
        return

    # === ОБЫЧНАЯ ОТПРАВКА ===
    account = data.get('account', 'accessories')
    acc_name = "Аксессуары" if account == 'accessories' else "Дианы"

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

        category_name = "Обычные" if data['category'] == 'usual' else "Крупные"

        info_msg = (
            f"📊 Детали отправки:\n\n"
            f"👤 Аккаунт: <b>{acc_name}</b>\n"
            f"📁 Категория групп: <b>{category_name}</b>\n"
            f"📷 Фото: <b>{len(data['photos'])}</b>\n"
            f"✅ Успешно: <b>{report.count('✅')}</b>\n"
            f"❌ Ошибок: <b>{report.count('❌')}</b>"
        )
        bot.send_message(chat_id, info_msg, parse_mode='HTML', reply_markup=main_kb())

    except Exception as e:
        err_msg = str(e)
        print(f"[FATAL] {err_msg}")
        bot.send_message(chat_id, f"🔥 Ошибка:\n\n{err_msg}", reply_markup=main_kb())
    finally:
        user_data[chat_id] = {'state': 'main'}

@bot.message_handler(func=lambda m: m.text == "🔄 Изменить")
def reset_ad(message):
    chat_id = message.chat.id
    state = get_user_state(chat_id)
    data = get_user_data(chat_id)

    if state not in ['confirm', 'schedule_confirm']:
        return

    mode = data.get('mode', 'instant')

    # Удаляем временные фото только для instant режима
    if mode == 'instant':
        for p in data.get('photos', []):
            try:
                if os.path.exists(p) and 'scheduled_photos' not in p:
                    os.remove(p)
            except:
                pass

    init_user_data(chat_id, mode=mode)
    print(f"[RESET] Пользователь {chat_id} сбросил объявление")
    bot.send_message(
        chat_id,
        "🔄 Начнём заново. Через какой аккаунт отправляем?",
        reply_markup=account_inline_kb()
    )

# ============ ПРОСМОТР ЗАПЛАНИРОВАННОГО ============

@bot.callback_query_handler(func=lambda call: call.data.startswith('sched_'))
def show_scheduled_detail(call):
    chat_id = call.message.chat.id
    ad_id = int(call.data.replace('sched_', ''))

    ad = get_scheduled_ad_by_id(ad_id)
    if not ad or ad['chat_id'] != chat_id:
        bot.answer_callback_query(call.id, "❌ Объявление не найдено")
        return

    user_data[chat_id] = {
        'state': 'scheduled_detail',
        'viewing_ad_id': ad_id,
        'viewing_ad': ad
    }

    account_name = "Аксессуары" if ad['account'] == 'accessories' else "Дианы"
    category_name = "Обычные" if ad['category'] == 'usual' else "Крупные"
    days_str = format_days(ad['days'])

    photos = ad.get('photos', [])
    if photos:
        caption = (
            f"{ad['text']}\n\n"
            f"📊 Детали:\n"
            f"👤 Аккаунт: {account_name}\n"
            f"📁 Группы: {category_name}\n"
            f"📅 Дни: {days_str}\n"
            f"⏰ Время: {ad['time']}"
        )
        send_photos_as_album(chat_id, photos, caption=caption)
    else:
        detail_msg = (
            f"{ad['text']}\n\n"
            f"📊 Детали:\n"
            f"👤 Аккаунт: <b>{account_name}</b>\n"
            f"📁 Группы: <b>{category_name}</b>\n"
            f"📅 Дни: <b>{days_str}</b>\n"
            f"⏰ Время: <b>{ad['time']}</b>"
        )
        bot.send_message(chat_id, detail_msg, parse_mode='HTML')

    bot.send_message(chat_id, "Выберите действие:", reply_markup=scheduled_detail_kb())
    bot.answer_callback_query(call.id)

# ============ ИЗМЕНЕНИЕ ЗАПЛАНИРОВАННОГО ============

@bot.message_handler(func=lambda m: m.text == "📝 Изменить объявление" and get_user_state(m.chat.id) == 'scheduled_detail')
def edit_ad_text(message):
    chat_id = message.chat.id
    ad_id = get_user_data(chat_id).get('viewing_ad_id')

    if ad_id:
        delete_scheduled_ad(ad_id)

    init_user_data(chat_id, mode='schedule')
    bot.send_message(
        chat_id,
        "📝 Изменение объявления\n\nНачнём заново. Через какой аккаунт отправляем?",
        reply_markup=account_inline_kb()
    )

@bot.message_handler(func=lambda m: m.text == "👤 Изменить аккаунт" and get_user_state(m.chat.id) == 'scheduled_detail')
def edit_account(message):
    chat_id = message.chat.id
    ad_id = get_user_data(chat_id).get('viewing_ad_id')

    user_data[chat_id]['state'] = 'edit_account'
    user_data[chat_id]['editing_ad_id'] = ad_id
    bot.send_message(
        chat_id,
        "👤 Выберите новый аккаунт:",
        reply_markup=account_inline_kb()
    )

@bot.message_handler(func=lambda m: m.text == "📁 Изменить группы" and get_user_state(m.chat.id) == 'scheduled_detail')
def edit_groups(message):
    chat_id = message.chat.id
    ad_id = get_user_data(chat_id).get('viewing_ad_id')

    user_data[chat_id]['state'] = 'edit_groups'
    user_data[chat_id]['editing_ad_id'] = ad_id
    bot.send_message(
        chat_id,
        "📁 Выберите новые группы:",
        reply_markup=category_kb()
    )

@bot.message_handler(func=lambda m: m.text == "📅 Изменить дни публикации" and get_user_state(m.chat.id) == 'scheduled_detail')
def edit_days(message):
    chat_id = message.chat.id
    ad_id = get_user_data(chat_id).get('viewing_ad_id')

    user_data[chat_id]['state'] = 'edit_days'
    user_data[chat_id]['editing_ad_id'] = ad_id
    user_data[chat_id]['temp_days'] = []

    bot.send_message(
        chat_id,
        "📅 Выберите новые дни недели:",
        reply_markup=days_inline_kb([])
    )

@bot.message_handler(func=lambda m: m.text == "⏰ Изменить время публикации" and get_user_state(m.chat.id) == 'scheduled_detail')
def edit_time(message):
    chat_id = message.chat.id
    ad_id = get_user_data(chat_id).get('viewing_ad_id')

    user_data[chat_id]['state'] = 'edit_time'
    user_data[chat_id]['editing_ad_id'] = ad_id
    bot.send_message(
        chat_id,
        "⏰ Введите новое время (формат 16:00):",
        reply_markup=back_kb()
    )

@bot.message_handler(func=lambda m: m.text == "🗑 Удалить объявление" and get_user_state(m.chat.id) == 'scheduled_detail')
def delete_ad(message):
    chat_id = message.chat.id
    ad_id = get_user_data(chat_id).get('viewing_ad_id')

    if ad_id:
        ad = get_scheduled_ad_by_id(ad_id)
        if ad:
            # Удаляем фото с диска
            for p in ad.get('photos', []):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except:
                    pass
        delete_scheduled_ad(ad_id)

    bot.send_message(chat_id, "🗑 Объявление удалено", reply_markup=main_kb())
    set_user_state(chat_id, 'main')
    show_scheduled_list(chat_id)

@bot.message_handler(func=lambda m: get_user_state(m.chat.id) == 'edit_time')
def save_edited_time(message):
    chat_id = message.chat.id
    time_str = message.text.strip()
    data = get_user_data(chat_id)
    ad_id = data.get('editing_ad_id')

    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        bot.send_message(chat_id, "❌ Неверный формат. Введите время как 16:00", reply_markup=back_kb())
        return

    ad = get_scheduled_ad_by_id(ad_id)

    if ad and check_time_conflict(chat_id, ad['days'], time_str, exclude_id=ad_id):
        bot.send_message(
            chat_id,
            "❌ К сожалению, это время уже занято. Выберите другое время:",
            reply_markup=back_kb()
        )
        return

    update_scheduled_ad(ad_id, {'time': time_str})
    bot.send_message(chat_id, f"✅ Время изменено на: {time_str}", reply_markup=main_kb())
    set_user_state(chat_id, 'main')
    show_scheduled_list(chat_id)

# ============ КНОПКА НАЗАД ============

@bot.message_handler(func=lambda m: m.text == "◀️ Назад")
def go_back(message):
    chat_id = message.chat.id
    state = get_user_state(chat_id)
    data = get_user_data(chat_id)

    if state == 'time':
        user_data[chat_id]['state'] = 'days'
        days = data.get('days', [])
        days_str = format_days(days)
        if days:
            msg = f"Выбрано: {days_str}\n\nВыбрать ещё?"
        else:
            msg = "Выберите дни недели:"
        bot.send_message(chat_id, msg, reply_markup=days_inline_kb(days))

    elif state == 'days':
        user_data[chat_id]['state'] = 'text'
        bot.send_message(chat_id, "✏️ Отправь текст объявления:", reply_markup=back_kb())

    elif state == 'text':
        user_data[chat_id]['state'] = 'photo'
        bot.send_message(
            chat_id,
            "📷 Отправь фото (до 10 шт.). Когда закончишь — нажми кнопку ниже.",
            reply_markup=photo_kb()
        )

    elif state == 'photo':
        user_data[chat_id]['state'] = 'category'
        bot.send_message(chat_id, "Выбери категорию:", reply_markup=category_kb())

    elif state == 'category':
        user_data[chat_id]['state'] = 'account'
        bot.send_message(
            chat_id,
            "Через какой аккаунт отправляем?",
            reply_markup=account_inline_kb()
        )

    elif state in ['scheduled_detail', 'edit_account', 'edit_groups', 'edit_days', 'edit_time', 'scheduled_list']:
        set_user_state(chat_id, 'main')
        bot.send_message(chat_id, "👋 Главное меню", reply_markup=main_kb())

    elif state in ['confirm', 'schedule_confirm']:
        user_data[chat_id]['state'] = 'text'
        bot.send_message(chat_id, "✏️ Отправь текст объявления:", reply_markup=back_kb())

    else:
        user_data[chat_id] = {'state': 'main'}
        bot.send_message(chat_id, "👋 Главное меню", reply_markup=main_kb())

# ============ ПЛАНИРОВЩИК ============

def run_scheduler():
    """Фоновый поток для проверки расписания — каждые 30 секунд"""
    print("[SCHEDULER] Поток планировщика запущен")
    while True:
        try:
            check_and_send_scheduled()
        except Exception as e:
            print(f"[SCHEDULER LOOP ERROR] {e}")
        time.sleep(30)

# Храним последнее проверенное время, чтобы не отправлять дважды
_last_checked_minute = None

def check_and_send_scheduled():
    """Проверяет и отправляет запланированные объявления"""
    global _last_checked_minute
    from db_worker import get_due_ads, mark_ad_sent

    now = datetime.now()
    current_minute = now.strftime('%H:%M')

    # Проверяем только если минута изменилась
    if _last_checked_minute == current_minute:
        return
    _last_checked_minute = current_minute

    weekday_map = {0: 'mon', 1: 'tue', 2: 'wed', 3: 'thu', 4: 'fri', 5: 'sat', 6: 'sun'}
    current_day_code = weekday_map.get(now.weekday(), '')

    print(f"[SCHEDULER CHECK] {now} | day={current_day_code} | time={current_minute}")

    if not current_day_code:
        return

    due_ads = get_due_ads(current_day_code, current_minute)
    print(f"[SCHEDULER] Найдено {len(due_ads)} объявлений для отправки")

    for ad in due_ads:
        chat_id = ad['chat_id']
        try:
            print(f"[SCHEDULER] Отправка объявления id={ad['id']} для chat_id={chat_id}")
            status_msg = bot.send_message(chat_id, "⏳ Начинаю отправку объявления...")

            account = ad.get('account', 'accessories')
            acc_name = "Аксессуары" if account == 'accessories' else "Дианы"

            # Проверяем что фото существуют
            valid_photos = [p for p in ad['photos'] if os.path.exists(p)]
            if len(valid_photos) != len(ad['photos']):
                missing = len(ad['photos']) - len(valid_photos)
                print(f"[SCHEDULER WARNING] {missing} фото не найдено!")

            report = send_to_vk_groups(
                ad['text'],
                valid_photos,
                ad['category'],
                account=account
            )

            try:
                bot.delete_message(chat_id, status_msg.message_id)
            except:
                pass

            bot.send_message(
                chat_id,
                f"📋 Объявление отправлено!\n\n{report}",
                reply_markup=main_kb()
            )

            category_name = "Обычные" if ad['category'] == 'usual' else "Крупные"
            info_msg = (
                f"📊 Детали отправки:\n\n"
                f"👤 Аккаунт: <b>{acc_name}</b>\n"
                f"📁 Категория групп: <b>{category_name}</b>\n"
                f"📷 Фото: <b>{len(valid_photos)}</b>\n"
                f"✅ Успешно: <b>{report.count('✅')}</b>\n"
                f"❌ Ошибок: <b>{report.count('❌')}</b>"
            )
            bot.send_message(chat_id, info_msg, parse_mode='HTML', reply_markup=main_kb())

            mark_ad_sent(ad['id'], current_day_code)
            print(f"[SCHEDULER] Объявление {ad['id']} успешно отправлено")

        except Exception as e:
            print(f"[SCHEDULER ERROR] Ad {ad['id']}: {e}")
            try:
                bot.send_message(chat_id, f"🔥 Ошибка при отправке запланированного объявления:\n\n{str(e)}", reply_markup=main_kb())
            except:
                pass

# ============ FALLBACK ============

@bot.message_handler(func=lambda m: True)
def fallback(message):
    bot.send_message(message.chat.id, "❓ Нажми /start если что-то пошло не так.", reply_markup=main_kb())

@app.route('/')
def index():
    return "OK", 200

def run_bot():
    reset_webhook()
    print("[Bot] Старт polling...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

if __name__ == '__main__':
    print(f"[Server] Flask на порту {PORT}")
    print(f"[Storage] Фото хранятся в: {PHOTO_STORAGE}")
    print(f"[Time] Текущее время сервера: {datetime.now()}")

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    print("[Scheduler] Планировщик запущен")

    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=PORT)
