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

load_dotenv()

TG_TOKEN = os.getenv('TG_TOKEN')
raw_port = os.getenv('PORT')
try:
    PORT = int(raw_port) if raw_port and raw_port.lower() not in ('null', '', 'none') else 80
except ValueError:
    PORT = 80

# URL мини-приложения (на Amvera будет типа https://твой-проект.amvera.io/miniapp/)
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
        parsed_data = dict(x.split('=') for x in init_data.split('&'))
        hash_value = parsed_data.pop('hash', None)
        
        data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        secret_key = hmac.new(b"WebAppData", TG_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash != hash_value:
            return None
            
        auth_date = int(parsed_data.get('auth_date', 0))
        if time.time() - auth_date > 86400:
            return None
            
        return json.loads(parsed_data.get('user', '{}'))
    except Exception as e:
        print(f"[VERIFY ERROR] {e}")
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
# Раздача Mini App
# ═══════════════════════════════════════

@app.route('/miniapp/')
def serve_miniapp():
    return send_from_directory('miniapp', 'index.html')

@app.route('/miniapp/<path:path>')
def serve_miniapp_static(path):
    return send_from_directory('miniapp', path)

@app.route('/')
def index():
    return "OK", 200

# ═══════════════════════════════════════
# Бот (старые ручки оставляем + новая)
# ═══════════════════════════════════════

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

# ... (остальные старые хендлеры без изменений, если нужно — скопируй из своего файла) ...

def run_bot():
    reset_webhook()
    print("[Bot] Старт polling...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

if __name__ == '__main__':
    print(f"[Server] Flask на порту {PORT}")
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=PORT)
