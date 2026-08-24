import os
import vk_api
from dotenv import load_dotenv

load_dotenv()

_session_cache = {}

def auth_handler(account='accessories'):
    """Обработчик двухфакторной аутентификации"""
    # В контейнере нельзя вводить интерактивно, поэтому просто логируем
    print(f"[VK_AUTH] Требуется 2FA для {account}!")
    raise Exception(f"2FA требуется для {account}. Отключите 2FA в настройках VK или используйте готовый токен.")

def captcha_handler(captcha):
    """Обработчик капчи"""
    print(f"[VK_AUTH] Требуется капча: {captcha.get_url()}")
    raise Exception("Требуется капча. Используйте готовый токен.")

def get_vk_session(account='accessories'):
    """
    Получает VK API сессию.
    Сначала пробует логин/пароль, если не указаны - использует готовый токен.
    """
    global _session_cache

    cache_key = account
    if cache_key in _session_cache:
        return _session_cache[cache_key]

    if account == 'accessories':
        login = os.getenv('VK_LOGIN')
        password = os.getenv('VK_PASSWORD')
        token = os.getenv('VK_TOKEN')
    else:
        login = os.getenv('VK_LOGIN2')
        password = os.getenv('VK_PASSWORD2')
        token = os.getenv('VK_TOKEN2')

    # Если есть логин/пароль - авторизуемся через них
    if login and password:
        try:
            print(f"[VK_AUTH] Авторизация {account} через логин/пароль ({login})...")
            vk_session = vk_api.VkApi(
                login=login,
                password=password,
                auth_handler=lambda: auth_handler(account),
                captcha_handler=captcha_handler,
                app_id=2685278,  # Kate Mobile
                scope=268435455  # offline, photos, wall, groups и всё остальное
            )
            vk_session.auth()
            _session_cache[cache_key] = vk_session
            # Сохраняем полученный токен в кэш для информации
            new_token = vk_session.token['access_token']
            print(f"[VK_AUTH] Авторизация {account} успешна! Новый токен: {new_token[:20]}...")
            return vk_session
        except Exception as e:
            print(f"[VK_AUTH] Ошибка авторизации через логин/пароль: {e}")
            print(f"[VK_AUTH] Пробую использовать готовый токен...")

    # Fallback: используем готовый токен
    if token:
        try:
            print(f"[VK_AUTH] Использую готовый токен для {account}")
            vk_session = vk_api.VkApi(token=token)
            # Проверяем что токен рабочий
            vk = vk_session.get_api()
            me = vk.users.get()[0]
            print(f"[VK_AUTH] Токен рабочий. Пользователь: {me['first_name']} {me['last_name']}")
            _session_cache[cache_key] = vk_session
            return vk_session
        except Exception as e:
            print(f"[VK_AUTH] Готовый токен не работает: {e}")

    raise Exception(
        f"Не удалось авторизоваться в VK для аккаунта '{account}'.\n"
        f"Варианты:\n"
        f"1. Укажите VK_LOGIN + VK_PASSWORD (или VK_LOGIN2 + VK_PASSWORD2)\n"
        f"2. Или укажите рабочий VK_TOKEN / VK_TOKEN2"
    )

def get_vk_api(account='accessories'):
    """Получает VK API объект"""
    session = get_vk_session(account)
    return session.get_api()

