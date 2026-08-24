import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

_api_cache = {}

def get_vk_token_direct(account='accessories'):
    """
    Получает токен VK через прямую авторизацию (Direct Auth).
    Эмулирует официальное Android-приложение VK.
    """
    if account == 'accessories':
        login = os.getenv('VK_LOGIN')
        password = os.getenv('VK_PASSWORD')
    else:
        login = os.getenv('VK_LOGIN2')
        password = os.getenv('VK_PASSWORD2')

    if not login or not password:
        raise Exception(f"Не указаны логин/пароль для '{account}'")

    print(f"[VK_AUTH] Прямая авторизация {account} ({login})...")

    # Direct authorization endpoint (used by official VK Android app)
    url = "https://oauth.vk.com/token"
    params = {
        'grant_type': 'password',
        'client_id': '2274003',  # VK Android
        'client_secret': 'hHbZxrka2uZ6jB1inYsH',
        'username': login,
        'password': password,
        'scope': 'offline,photos,wall,groups',
        'v': '5.199'
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        data = response.json()

        if 'error' in data:
            error_msg = data.get('error_description', data['error'])
            print(f"[VK_AUTH] Ошибка: {error_msg}")
            raise Exception(f"VK auth error: {error_msg}")

        token = data['access_token']
        user_id = data.get('user_id', '?')
        print(f"[VK_AUTH] Успешно! user_id={user_id}, token={token[:20]}...")
        return token

    except Exception as e:
        print(f"[VK_AUTH] Ошибка запроса: {e}")
        raise

def get_vk_api(account='accessories'):
    """Получает VK API сессию через vk_api с автоматически полученным токеном"""
    global _api_cache

    if account in _api_cache:
        return _api_cache[account]

    import vk_api

    token = get_vk_token_direct(account)
    vk_session = vk_api.VkApi(token=token)
    api = vk_session.get_api()

    # Проверяем
    me = api.users.get()[0]
    print(f"[VK_AUTH] API готов. Пользователь: {me['first_name']} {me['last_name']}")

    _api_cache[account] = api
    return api