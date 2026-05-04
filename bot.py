import os
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)
import requests
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from vk_worker import send_to_vk_groups
from dotenv import load_dotenv
import hashlib
import hmac
import time
import json
from urllib.parse import unquote

load_dotenv()

TG_TOKEN = os.getenv('TG_TOKEN', '').strip()
raw_port = os.getenv('PORT')
try:
    PORT = int(raw_port) if raw_port and raw_port.lower() not in ('null', '', 'none') else 80
except ValueError:
    PORT = 80

MINIAPP_URL = os.getenv('MINIAPP_URL', '')

bot = telebot.TeleBot(TG_TOKEN)
app = Flask(__name__)
CORS(app)

user_data = {}

# ═══════════════════════════════════════
# Проверка подписи initData от Telegram
# ═══════════════════════════════════════
def verify_telegram_init_data(init_data):
    try:
        if not init_data:
            print("[VERIFY] ❌ init_data пустой")
            return None
        
        print(f"[VERIFY] init_data length: {len(init_data)}")
        print(f"[VERIFY] TG_TOKEN length: {len(TG_TOKEN)}")
        print(f"[VERIFY] TG_TOKEN first 15: {TG_TOKEN[:15]}...")
        
        # Парсим query string корректно — только по первому '='
        parsed_data = {}
        for pair in init_data.split('&'):
            if '=' in pair:
                key, value = pair.split('=', 1)
                parsed_data[key] = value
        
        print(f"[VERIFY] Keys found: {list(parsed_data.keys())}")
        
        hash_value = parsed_data.pop('hash', None)
        if not hash_value:
            print("[VERIFY] ❌ hash отсутствует")
            return None
        
        # Собираем data_check_string из отсортированных пар
        data_check_string = '\n'.join(
            f"{k}={parsed_data[k]}" 
            for k in sorted(parsed_data.keys())
        )
        
        print(f"[VERIFY] data_check_string preview: {data_check_string[:120]}...")
        
        secret_key = hmac.new(b"WebAppData", TG_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        print(f"[VERIFY] calculated hash: {calculated_hash[:20]}...")
        print(f"[VERIFY] received hash:   {hash_value[:20]}...")
        
        if calculated_hash != hash_value:
            print(f"[VERIFY] ❌ hash НЕ СОВПАДАЕТ")
            return None
            
        auth_date = int(parsed_data.get('auth_date', 0))
        print(f"[VERIFY] auth_date: {auth_date}, now: {int(time.time())}, diff: {int(time.time()) - auth_date}")
        
        if time.time() - auth_date > 86400:
            print("[VERIFY] ❌ auth_date просрочен")
            return None
        
        # user приходит URL-encoded — декодируем
        user_raw = parsed_data.get('user', '{}')
        user_json = unquote(user_raw)
        user_obj = json.loads(user_json)
        print(f"[VERIFY] ✅ User ID: {user_obj.get('id')}")
        return user_obj
        
    except Exception as e:
        print(f"[VERIFY ERROR] {e}")
        import traceback
        traceback.print_exc()
        return None

# ═══════════════════════════════════════
# API для Mini App
# ═══════════════════════════════════════

@app.route('/api/groups', methods=['POST'])
def api_get_groups():
    data = request.json or {}
    user = verify_telegram_init_data(data.get('initData', ''))
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    account = data.get('account', 'accessories')
    
    if account == 'accessories':
        usual = os.getenv('GROUPS_USUAL', '')
        large = os.getenv('GROUPS_LARGE', '')
    else:
        usual = os.getenv('GROUPS_USUAL2', os.getenv('GROUPS_USUAL', ''))
        large = os.getenv('GROUPS_LARGE2', os.getenv('GROUPS_LARGE', ''))
    
    all_groups = []
    seen = set()
    
    for category, env_str in [('usual', usual), ('large', large)]:
        for g in env_str.split(','):
            g = g.strip()
            if g and g not in seen:
                seen.add(g)
                all_groups.append({
                    'id': g,
                    'name': f'Группа {g}',
                    'category': category
                })
    
    return jsonify({'groups': all_groups})

@app.route('/api/upload-photos', methods=['POST'])
def api_upload_photos():
    init_data = request.form.get('initData', '')
    user = verify_telegram_init_data(init_data)
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = str(user.get('id'))
    tmp_dir = f"temp/{user_id}"
    os.makedirs(tmp_dir, exist_ok=True)
    
    saved_paths = []
    for key in request.files:
        file = request.files[key]
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1] or '.jpg'
            filename = f"photo_{int(time.time()*1000)}_{len(saved_paths)}{ext}"
            path = os.path.join(tmp_dir, filename)
            file.save(path)
            saved_paths.append(path)
    
    return jsonify({'photos': saved_paths})

@app.route('/api/send', methods=['POST'])
def api_send():
    data = request.json or {}
    user = verify_telegram_init_data(data.get('initData', ''))
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    account = data.get('account', 'accessories')
    category = data.get('category', 'usual')
    text = data.get('text', '')
    photos = data.get('photos', [])
    selected_groups = data.get('selected_groups', None)
    
    try:
        report, detailed = send_to_vk_groups(
            text, photos, category, account=account, 
            selected_groups=selected_groups
        )
        
        for p in photos:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except:
                pass
                
        return jsonify({
            'success': True,
            'report': report,
            'detailed': detailed
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ═══════════════════════════════════════
# Раздача Mini App с КОРНЯ домена
# ═══════════════════════════════════════

@app.route('/')
def serve_root():
    return send_from_directory('miniapp', 'index.html')

@app.route('/<path:filename>')
def serve_root_static(filename):
    if filename.startswith('api/'):
        return "Not found", 404
    return send_from_directory('miniapp', filename)

# ═══════════════════════════════════════
# Бот
# ═══════════════════════════════════════

def reset_webhook():
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/setWebhook?url="
        r = requests.get(url, timeout=10)
        print(f"[Webhook] Сброшен: {r.status_code} | {r.text}")
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
        InlineKeyboardButton("Дианы", callback_data='acc_autosale')
    )
    return kb

@bot.message_handler(commands=['start'])
def cmd_start(message):
    chat_id = message.chat.id
    user_data[chat_id] = {'state': 'main'}
    
    if MINIAPP_URL:
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("🚀 Открыть Mini App", web_app=WebAppInfo(url=MINIAPP_URL)))
        kb.add(KeyboardButton("📱 Отправить через бота"))
        bot.send_message(chat_id, "👋 Привет, Захар!\n\nВыбери, как удобнее отправить объявление:", reply_markup=kb)
    else:
        bot.send_message(chat_id, "👋 Привет! Нажми кнопку ниже.", reply_markup=main_kb())

@bot.message_handler(func=lambda m: m.text == "📱 Отправить через бота")
def send_ad_old(message):
    chat_id = message.chat.id
    user_data[chat_id] = {
        'state': 'account',
        'photos': [], 'text': '', 'category': None, 'account': None
    }
    bot.send_message(chat_id, "Через какой аккаунт отправляем?", reply_markup=account_inline_kb())

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
        f"👤 Аккаунт: {'Аксессуары' if user_data[chat_id]['account'] == 'accessories' else 'Дианы'}"
    )
    bot.send_message(chat_id, preview, reply_markup=confirm_kb())

@bot.message_handler(func=lambda m: m.text == "Готово ☑️")
def confirm_send(message):
    chat_id = message.chat.id
    if user_data.get(chat_id, {}).get('state') != 'confirm':
        return

    data = user_data[chat_id]
    account = data.get('account', 'accessories')
    acc_name = 'Аксессуары' if account == 'accessories' else 'Дианы'

    print(f"[CONFIRM] Отправка: {len(data['photos'])} фото, аккаунт: {acc_name}")

    for p in data['photos']:
        exists = os.path.exists(p)
        size = os.path.getsize(p) if exists else 0
        print(f"[CHECK] {p} | exists={exists} | size={size}")

    bot.send_message(chat_id, f"⏳ Отправляю через <b>{acc_name}</b>...", parse_mode='HTML')

    try:
        report, _ = send_to_vk_groups(
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

def run_bot():
    reset_webhook()
    print("[Bot] Старт polling...")
    bot.infinity_polling(
        timeout=60, 
        long_polling_timeout=60,
        skip_pending=True
    )

if __name__ == '__main__':
    print(f"[Server] Flask на порту {PORT}")
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=PORT)
