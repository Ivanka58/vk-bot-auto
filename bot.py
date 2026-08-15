import os
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
import requests
import threading
from flask import Flask
from vk_worker import send_to_vk_groups
from dotenv import load_dotenv
import schedule
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
    kb.add(KeyboardButton("📤 Отправить объявление"), KeyboardButton("📅 Запланировать отправку"))
    return kb

def back_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("◀️ Назад"))
    return kb

def category_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📁 Обычные группы"), KeyboardButton("⭐ Крупные группы"))
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

def days_inline_kb(selected_days=None, finish_only=False):
    if selected_days is None:
        selected_days = []
    kb = InlineKeyboardMarkup()
    days = [('Пн', 'mon'), ('Вт', 'tue'), ('Ср', 'wed'), ('Чт', 'thu'), ('Пт', 'fri'), ('Сб', 'sat'), ('Вс', 'sun')]

    if finish_only:
        kb.add(InlineKeyboardButton("✅ Закончить", callback_data='days_finish'))
        return kb

    row = []
    for name, code in days:
        if code not in selected_days:
            row.append(InlineKeyboardButton(name, callback_data=f'day_{code}'))
        else:
            row.append(InlineKeyboardButton(f"✅ {name}", callback_data=f'day_{code}'))
    kb.row(*row)

    if selected_days:
        kb.add(InlineKeyboardButton("✅ Закончить выбор", callback_data='days_finish'))
    return kb

def scheduled_detail_kb(ad_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📝 Изменить объявление"))
    kb.add(KeyboardButton("👤 Изменить аккаунт"))
    kb.add(KeyboardButton("📁 Изменить группы"))
    kb.add(KeyboardButton("📅 Изменить дни публикации"))
    kb.add(KeyboardButton("⏰ Изменить время публикации"))
    kb.add(KeyboardButton("◀️ Назад"))
    return kb

def scheduled_list_kb(ads):
    kb = InlineKeyboardMarkup()
    day_names = {'mon': 'пн', 'tue': 'вт', 'wed': 'ср', 'thu': 'чт', 'fri': 'пт', 'sat': 'сб', 'sun': 'вс'}
    for ad in ads:
        days_str = ', '.join([day_names.get(d, d) for d in ad['days']])
        label = f"{days_str} — {ad['time']}"
        kb.add(InlineKeyboardButton(label, callback_data=f'sched_{ad["id"]}'))
    kb.add(InlineKeyboardButton("➕ Добавить ещё", callback_data='sched_add'))
    return kb

def format_days(days):
    day_names = {'mon': 'понедельник', 'tue': 'вторник', 'wed': 'среда', 'thu': 'четверг', 'fri': 'пятница', 'sat': 'суббота', 'sun': 'воскресенье'}
    order = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    result = []
    for d in order:
        if d in days:
            result.append(day_names[d])
    return ', '.join(result)

def format_days_short(days):
    day_names = {'mon': 'пн', 'tue': 'вт', 'wed': 'ср', 'thu': 'чт', 'fri': 'пт', 'sat': 'сб', 'sun': 'вс'}
    order = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    result = []
    for d in order:
        if d in days:
            result.append(day_names[d])
    return ', '.join(result)

# ============ ОБЩИЕ ОБРАБОТЧИКИ ============

@bot.message_handler(commands=['start'])
def cmd_start(message):
    chat_id = message.chat.id
    user_data[chat_id] = {'state': 'main'}

    # Проверяем есть ли запланированные объявления
    ads = get_scheduled_ads(chat_id)
    if ads:
        msg = "👋 Привет! У вас есть запланированные объявления. Выберите действие:"
        bot.send_message(chat_id, msg, reply_markup=main_kb())
        show_scheduled_list(chat_id)
    else:
        bot.send_message(chat_id, "👋 Привет! Нажми кнопку ниже.", reply_markup=main_kb())

def show_scheduled_list(chat_id):
    ads = get_scheduled_ads(chat_id)
    if not ads:
        bot.send_message(chat_id, "📭 У вас пока нет запланированных объявлений.", reply_markup=main_kb())
        return

    msg = "📅 Ваши запланированные объявления:"
    kb = scheduled_list_kb(ads)
    bot.send_message(chat_id, msg, reply_markup=kb)

# ============ ОБЫЧНАЯ ОТПРАВКА (как было) ============

@bot.message_handler(func=lambda m: m.text == "📤 Отправить объявление")
def send_ad(message):
    chat_id = message.chat.id
    user_data[chat_id] = {
        'state': 'account',
        'photos': [], 'text': '', 'category': None, 'account': None,
        'mode': 'instant'
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

    name = "Аксессуары" if account == 'accessories' else "Дианы"
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
        return bot.send_message(chat_id, "❌ Лимит 10 фото. Нажми «✅ Закончить отправку фото»")

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
        f"📷 Фото {len(photos)}/10. Можешь ещё или нажать «✅ Закончить отправку фото»",
        reply_markup=photo_kb()
    )

@bot.message_handler(func=lambda m: m.text == "✅ Закончить отправку фото")
def finish_photos(message):
    chat_id = message.chat.id
    if user_data.get(chat_id, {}).get('state') != 'photo':
        return
    if not user_data[chat_id]['photos']:
        return bot.send_message(chat_id, "❌ Ни одного фото. Отправь хотя бы одно.")

    user_data[chat_id]['state'] = 'text'
    print(f"[FINISH] Файлы: {user_data[chat_id]['photos']}")
    from telebot.types import ReplyKeyboardRemove
    bot.send_message(chat_id, "✏️ Теперь отправь текст объявления:", reply_markup=ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: user_data.get(m.chat.id, {}).get('state') == 'text')
def handle_text(message):
    chat_id = message.chat.id
    user_data[chat_id]['text'] = message.text
    user_data[chat_id]['state'] = 'confirm'

    account = user_data[chat_id].get('account', 'accessories')
    acc_name = "Аксессуары" if account == 'accessories' else "Дианы"

    preview = (
        f"📋 Предпросмотр:\n\n"
        f"{message.text}\n\n"
        f"📷 Фото: {len(user_data[chat_id]['photos'])}\n"
        f"👤 Аккаунт: {acc_name}"
    )
    bot.send_message(chat_id, preview, reply_markup=confirm_kb())

@bot.message_handler(func=lambda m: m.text == "☑️ Готово")
def confirm_send(message):
    chat_id = message.chat.id
    if user_data.get(chat_id, {}).get('state') != 'confirm':
        return

    data = user_data[chat_id]

    # Если режим планирования — сохраняем в БД
    if data.get('mode') == 'schedule':
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

        # Чистим временные файлы
        for p in data.get('photos', []):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except:
                pass
        user_data[chat_id] = {'state': 'main'}
        return

    # Обычная отправка
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
        for p in data.get('photos', []):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except:
                pass
        user_data[chat_id] = {'state': 'main'}

@bot.message_handler(func=lambda m: m.text == "🔄 Изменить")
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
        'photos': [], 'text': '', 'category': None, 'account': None,
        'mode': user_data.get(chat_id, {}).get('mode', 'instant')
    }
    print(f"[RESET] Пользователь {chat_id} сбросил объявление")
    bot.send_message(
        chat_id,
        "Через какой аккаунт отправляем?",
        reply_markup=account_inline_kb()
    )

# ============ ЗАПЛАНИРОВАННАЯ ОТПРАВКА ============

@bot.message_handler(func=lambda m: m.text == "📅 Запланировать отправку")
def schedule_ad_start(message):
    chat_id = message.chat.id
    user_data[chat_id] = {
        'state': 'account',
        'photos': [], 'text': '', 'category': None, 'account': None,
        'mode': 'schedule', 'days': [], 'time': None
    }
    bot.send_message(
        chat_id,
        "📅 Запланировать отправку\n\nЧерез какой аккаунт отправляем?",
        reply_markup=account_inline_kb()
    )

# ============ ВЫБОР ДНЕЙ НЕДЕЛИ ============

@bot.callback_query_handler(func=lambda call: call.data.startswith('day_'))
def choose_day(call):
    chat_id = call.message.chat.id
    if user_data.get(chat_id, {}).get('state') != 'days':
        return

    day_code = call.data.replace('day_', '')
    days = user_data[chat_id]['days']

    if day_code in days:
        days.remove(day_code)
    else:
        days.append(day_code)

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
    if user_data.get(chat_id, {}).get('state') != 'days':
        return

    days = user_data[chat_id]['days']
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

@bot.message_handler(func=lambda m: user_data.get(m.chat.id, {}).get('state') == 'time')
def handle_time(message):
    chat_id = message.chat.id
    time_str = message.text.strip()

    # Проверка формата времени
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        bot.send_message(chat_id, "❌ Неверный формат. Введите время как 16:00")
        return

    # Проверка конфликта времени
    days = user_data[chat_id]['days']
    if check_time_conflict(chat_id, days, time_str):
        bot.send_message(
            chat_id,
            "❌ К сожалению, это время уже занято. Выберите другое время:",
            reply_markup=back_kb()
        )
        return

    user_data[chat_id]['time'] = time_str
    user_data[chat_id]['state'] = 'schedule_confirm'

    # Показываем предпросмотр
    data = user_data[chat_id]
    account = data.get('account', 'accessories')
    acc_name = "Аксессуары" if account == 'accessories' else "Дианы"
    category_name = "Обычные" if data['category'] == 'usual' else "Крупные"
    days_str = format_days(data['days'])

    # Отправляем фото
    for photo_path in data['photos']:
        with open(photo_path, 'rb') as f:
            bot.send_photo(chat_id, f)

    # Отправляем текст
    bot.send_message(chat_id, data['text'])

    # Отправляем сводку
    summary = (
        f"📋 Публикация объявления\n\n"
        f"👤 Выбран аккаунт: <b>{acc_name}</b>\n"
        f"📁 Выбраны группы: <b>{category_name}</b>\n"
        f"📅 Выбраны дни: <b>{days_str}</b>\n"
        f"⏰ Выбрано время: <b>{time_str}</b>\n\n"
        f"Всё готово?"
    )
    bot.send_message(chat_id, summary, parse_mode='HTML', reply_markup=confirm_kb())

# ============ СПИСОК ЗАПЛАНИРОВАННЫХ ============

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

    # Отправляем фото
    photos = ad.get('photos', [])
    if photos:
        for photo_path in photos:
            if os.path.exists(photo_path):
                with open(photo_path, 'rb') as f:
                    bot.send_photo(chat_id, f)

    # Отправляем текст и детали
    detail_msg = (
        f"{ad['text']}\n\n"
        f"📊 Детали:\n"
        f"👤 Аккаунт: <b>{account_name}</b>\n"
        f"📁 Группы: <b>{category_name}</b>\n"
        f"📅 Дни: <b>{days_str}</b>\n"
        f"⏰ Время: <b>{ad['time']}</b>"
    )
    bot.send_message(chat_id, detail_msg, parse_mode='HTML', reply_markup=scheduled_detail_kb(ad_id))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'sched_add')
def add_more_scheduled(call):
    chat_id = call.message.chat.id
    schedule_ad_start(call.message)
    bot.answer_callback_query(call.id)

# ============ ИЗМЕНЕНИЕ ЗАПЛАНИРОВАННОГО ============

@bot.message_handler(func=lambda m: m.text == "📝 Изменить объявление" and user_data.get(m.chat.id, {}).get('state') == 'scheduled_detail')
def edit_ad_text(message):
    chat_id = message.chat.id
    ad_id = user_data[chat_id]['viewing_ad_id']

    # Удаляем старое объявление и начинаем заново
    delete_scheduled_ad(ad_id)

    user_data[chat_id] = {
        'state': 'account',
        'photos': [], 'text': '', 'category': None, 'account': None,
        'mode': 'schedule', 'days': [], 'time': None
    }
    bot.send_message(
        chat_id,
        "📝 Изменение объявления\n\nНачнём заново. Через какой аккаунт отправляем?",
        reply_markup=account_inline_kb()
    )

@bot.message_handler(func=lambda m: m.text == "👤 Изменить аккаунт" and user_data.get(m.chat.id, {}).get('state') == 'scheduled_detail')
def edit_account(message):
    chat_id = message.chat.id
    ad_id = user_data[chat_id]['viewing_ad_id']

    user_data[chat_id]['state'] = 'edit_account'
    user_data[chat_id]['editing_ad_id'] = ad_id
    bot.send_message(
        chat_id,
        "👤 Выберите новый аккаунт:",
        reply_markup=account_inline_kb()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('acc_') and user_data.get(call.message.chat.id, {}).get('state') == 'edit_account')
def save_edited_account(call):
    chat_id = call.message.chat.id
    account = 'accessories' if call.data == 'acc_accessories' else 'autosale'
    ad_id = user_data[chat_id]['editing_ad_id']

    update_scheduled_ad(ad_id, {'account': account})

    name = "Аксессуары" if account == 'accessories' else "Дианы"
    bot.edit_message_text(
        f"✅ Аккаунт изменён на: <b>{name}</b>",
        chat_id=chat_id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id, f"Выбран: {name}")

    # Возвращаем к деталям
    show_scheduled_list(chat_id)
    user_data[chat_id] = {'state': 'main'}

@bot.message_handler(func=lambda m: m.text == "📁 Изменить группы" and user_data.get(m.chat.id, {}).get('state') == 'scheduled_detail')
def edit_groups(message):
    chat_id = message.chat.id
    ad_id = user_data[chat_id]['viewing_ad_id']

    user_data[chat_id]['state'] = 'edit_groups'
    user_data[chat_id]['editing_ad_id'] = ad_id
    bot.send_message(
        chat_id,
        "📁 Выберите новые группы:",
        reply_markup=category_kb()
    )

@bot.message_handler(func=lambda m: m.text in ["📁 Обычные группы", "⭐ Крупные группы"] and user_data.get(m.chat.id, {}).get('state') == 'edit_groups')
def save_edited_groups(message):
    chat_id = message.chat.id
    category = 'usual' if 'Обычные' in message.text else 'large'
    ad_id = user_data[chat_id]['editing_ad_id']

    update_scheduled_ad(ad_id, {'category': category})

    bot.send_message(chat_id, f"✅ Группы изменены на: {'Обычные' if category == 'usual' else 'Крупные'}", reply_markup=main_kb())
    show_scheduled_list(chat_id)
    user_data[chat_id] = {'state': 'main'}

@bot.message_handler(func=lambda m: m.text == "📅 Изменить дни публикации" and user_data.get(m.chat.id, {}).get('state') == 'scheduled_detail')
def edit_days(message):
    chat_id = message.chat.id
    ad_id = user_data[chat_id]['viewing_ad_id']

    user_data[chat_id]['state'] = 'edit_days'
    user_data[chat_id]['editing_ad_id'] = ad_id
    user_data[chat_id]['temp_days'] = []

    bot.send_message(
        chat_id,
        "📅 Выберите новые дни недели:",
        reply_markup=days_inline_kb([])
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('day_') and user_data.get(call.message.chat.id, {}).get('state') == 'edit_days')
def choose_edit_day(call):
    chat_id = call.message.chat.id
    day_code = call.data.replace('day_', '')
    days = user_data[chat_id]['temp_days']

    if day_code in days:
        days.remove(day_code)
    else:
        days.append(day_code)

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

@bot.callback_query_handler(func=lambda call: call.data == 'days_finish' and user_data.get(call.message.chat.id, {}).get('state') == 'edit_days')
def finish_edit_days(call):
    chat_id = call.message.chat.id
    days = user_data[chat_id]['temp_days']
    if not days:
        bot.answer_callback_query(call.id, "❌ Выберите хотя бы один день!")
        return

    ad_id = user_data[chat_id]['editing_ad_id']
    ad = get_scheduled_ad_by_id(ad_id)

    # Проверяем конфликт с другими объявлениями
    if check_time_conflict(chat_id, days, ad['time'], exclude_id=ad_id):
        bot.answer_callback_query(call.id, "❌ Конфликт времени с другим объявлением!")
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
    show_scheduled_list(chat_id)
    user_data[chat_id] = {'state': 'main'}

@bot.message_handler(func=lambda m: m.text == "⏰ Изменить время публикации" and user_data.get(m.chat.id, {}).get('state') == 'scheduled_detail')
def edit_time(message):
    chat_id = message.chat.id
    ad_id = user_data[chat_id]['viewing_ad_id']

    user_data[chat_id]['state'] = 'edit_time'
    user_data[chat_id]['editing_ad_id'] = ad_id
    bot.send_message(
        chat_id,
        "⏰ Введите новое время (формат 16:00):",
        reply_markup=back_kb()
    )

@bot.message_handler(func=lambda m: user_data.get(m.chat.id, {}).get('state') == 'edit_time')
def save_edited_time(message):
    chat_id = message.chat.id
    time_str = message.text.strip()
    ad_id = user_data[chat_id]['editing_ad_id']

    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        bot.send_message(chat_id, "❌ Неверный формат. Введите время как 16:00")
        return

    ad = get_scheduled_ad_by_id(ad_id)

    if check_time_conflict(chat_id, ad['days'], time_str, exclude_id=ad_id):
        bot.send_message(
            chat_id,
            "❌ К сожалению, это время уже занято. Выберите другое время:",
            reply_markup=back_kb()
        )
        return

    update_scheduled_ad(ad_id, {'time': time_str})
    bot.send_message(chat_id, f"✅ Время изменено на: {time_str}", reply_markup=main_kb())
    show_scheduled_list(chat_id)
    user_data[chat_id] = {'state': 'main'}

# ============ КНОПКА НАЗАД ============

@bot.message_handler(func=lambda m: m.text == "◀️ Назад")
def go_back(message):
    chat_id = message.chat.id
    state = user_data.get(chat_id, {}).get('state', 'main')

    # Маршрутизация назад
    if state in ['time', 'edit_time']:
        # Назад к выбору дней
        if state == 'edit_time':
            user_data[chat_id]['state'] = 'scheduled_detail'
            ad_id = user_data[chat_id].get('viewing_ad_id')
            if ad_id:
                # Показываем детали снова
                ad = get_scheduled_ad_by_id(ad_id)
                if ad:
                    account_name = "Аксессуары" if ad['account'] == 'accessories' else "Дианы"
                    category_name = "Обычные" if ad['category'] == 'usual' else "Крупные"
                    days_str = format_days(ad['days'])

                    photos = ad.get('photos', [])
                    if photos:
                        for photo_path in photos:
                            if os.path.exists(photo_path):
                                with open(photo_path, 'rb') as f:
                                    bot.send_photo(chat_id, f)

                    detail_msg = (
                        f"{ad['text']}\n\n"
                        f"📊 Детали:\n"
                        f"👤 Аккаунт: <b>{account_name}</b>\n"
                        f"📁 Группы: <b>{category_name}</b>\n"
                        f"📅 Дни: <b>{days_str}</b>\n"
                        f"⏰ Время: <b>{ad['time']}</b>"
                    )
                    bot.send_message(chat_id, detail_msg, parse_mode='HTML', reply_markup=scheduled_detail_kb(ad_id))
            return

        # Для нового объявления — назад к дням
        user_data[chat_id]['state'] = 'days'
        days = user_data[chat_id].get('days', [])
        days_str = format_days(days)
        if days:
            msg = f"Выбрано: {days_str}\n\nВыбрать ещё?"
        else:
            msg = "Выберите дни недели:"
        bot.send_message(chat_id, msg, reply_markup=days_inline_kb(days))

    elif state == 'days':
        # Назад к фото
        user_data[chat_id]['state'] = 'photo'
        bot.send_message(
            chat_id,
            "📷 Отправь фото (до 10 шт.). Когда закончишь — нажми кнопку ниже.",
            reply_markup=photo_kb()
        )

    elif state == 'photo':
        # Назад к категории
        user_data[chat_id]['state'] = 'category'
        bot.send_message(chat_id, "Выбери категорию:", reply_markup=category_kb())

    elif state == 'category':
        # Назад к аккаунту
        user_data[chat_id]['state'] = 'account'
        bot.send_message(
            chat_id,
            "Через какой аккаунт отправляем?",
            reply_markup=account_inline_kb()
        )

    elif state in ['scheduled_detail', 'edit_account', 'edit_groups', 'edit_days', 'edit_time']:
        # Назад к списку запланированных
        user_data[chat_id] = {'state': 'main'}
        show_scheduled_list(chat_id)

    elif state in ['text', 'confirm', 'schedule_confirm']:
        # Назад к фото
        user_data[chat_id]['state'] = 'photo'
        bot.send_message(
            chat_id,
            "📷 Отправь фото (до 10 шт.). Когда закончишь — нажми кнопку ниже.",
            reply_markup=photo_kb()
        )

    else:
        user_data[chat_id] = {'state': 'main'}
        bot.send_message(chat_id, "👋 Главное меню", reply_markup=main_kb())

# ============ ПЕРЕХВАТ СТЕЙТА ДЛЯ РЕЖИМА ПЛАНИРОВАНИЯ ============

# Переопределяем finish_photos для режима планирования
_original_finish_photos = finish_photos

@bot.message_handler(func=lambda m: m.text == "✅ Закончить отправку фото")
def finish_photos_schedule(message):
    chat_id = message.chat.id
    if user_data.get(chat_id, {}).get('state') != 'photo':
        return
    if not user_data[chat_id]['photos']:
        return bot.send_message(chat_id, "❌ Ни одного фото. Отправь хотя бы одно.")

    if user_data[chat_id].get('mode') == 'schedule':
        user_data[chat_id]['state'] = 'text'
        from telebot.types import ReplyKeyboardRemove
        bot.send_message(chat_id, "✏️ Теперь отправь текст объявления:", reply_markup=ReplyKeyboardRemove())
    else:
        # Обычный режим
        user_data[chat_id]['state'] = 'text'
        from telebot.types import ReplyKeyboardRemove
        bot.send_message(chat_id, "✏️ Теперь отправь текст объявления:", reply_markup=ReplyKeyboardRemove())

# Переопределяем handle_text для режима планирования
@bot.message_handler(func=lambda m: user_data.get(m.chat.id, {}).get('state') == 'text')
def handle_text_schedule(message):
    chat_id = message.chat.id
    user_data[chat_id]['text'] = message.text

    if user_data[chat_id].get('mode') == 'schedule':
        # Переходим к выбору дней
        user_data[chat_id]['state'] = 'days'
        user_data[chat_id]['days'] = []
        bot.send_message(
            chat_id,
            "📅 Выберите дни недели для отправки:",
            reply_markup=days_inline_kb([])
        )
    else:
        # Обычный режим
        user_data[chat_id]['state'] = 'confirm'
        account = user_data[chat_id].get('account', 'accessories')
        acc_name = "Аксессуары" if account == 'accessories' else "Дианы"
        preview = (
            f"📋 Предпросмотр:\n\n"
            f"{message.text}\n\n"
            f"📷 Фото: {len(user_data[chat_id]['photos'])}\n"
            f"👤 Аккаунт: {acc_name}"
        )
        bot.send_message(chat_id, preview, reply_markup=confirm_kb())

# ============ ПЛАНИРОВЩИК ============

def run_scheduler():
    """Фоновый поток для проверки расписания"""
    while True:
        schedule.run_pending()
        time.sleep(30)

def check_and_send_scheduled():
    """Проверяет и отправляет запланированные объявления"""
    from db_worker import get_due_ads, mark_ad_sent

    now = datetime.now()
    current_day = now.strftime('%a').lower()[:3]  # mon, tue, etc.
    # Преобразуем в наши коды
    day_map = {'mon': 'mon', 'tue': 'tue', 'wed': 'wed', 'thu': 'thu', 'fri': 'fri', 'sat': 'sat', 'sun': 'sun'}
    current_day_code = day_map.get(current_day, '')
    current_time = now.strftime('%H:%M')

    due_ads = get_due_ads(current_day_code, current_time)

    for ad in due_ads:
        chat_id = ad['chat_id']
        try:
            # Отправляем сообщение о начале
            status_msg = bot.send_message(chat_id, "⏳ Начинаю отправку объявления...")

            account = ad.get('account', 'accessories')
            acc_name = "Аксессуары" if account == 'accessories' else "Дианы"

            # Отправляем в ВК
            report = send_to_vk_groups(
                ad['text'],
                ad['photos'],
                ad['category'],
                account=account
            )

            # Удаляем статусное сообщение
            try:
                bot.delete_message(chat_id, status_msg.message_id)
            except:
                pass

            # Отправляем отчёт
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
                f"📷 Фото: <b>{len(ad['photos'])}</b>\n"
                f"✅ Успешно: <b>{report.count('✅')}</b>\n"
                f"❌ Ошибок: <b>{report.count('❌')}</b>"
            )
            bot.send_message(chat_id, info_msg, parse_mode='HTML', reply_markup=main_kb())

            # Отмечаем как отправленное (на сегодня)
            mark_ad_sent(ad['id'], current_day_code)

        except Exception as e:
            print(f"[SCHEDULER ERROR] Ad {ad['id']}: {e}")
            bot.send_message(chat_id, f"🔥 Ошибка при отправке запланированного объявления:\n\n{str(e)}", reply_markup=main_kb())

# Добавляем задачу в планировщик — проверка каждую минуту
schedule.every(1).minutes.do(check_and_send_scheduled)

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

    # Запускаем планировщик в отдельном потоке
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    print("[Scheduler] Планировщик запущен")

    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=PORT)
