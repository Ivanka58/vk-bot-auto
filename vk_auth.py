import os
import vk_api
from dotenv import load_dotenv

load_dotenv()

# Cache for sessions
_session_cache = {}

def auth_handler(account='accessories'):
    """Обработчик двухфакторной аутентификации"""
    key = input(f"Введите код 2FA для {account}: ")
    remember_device = True
    return key, remember_device

def captcha_handler(captcha):
    """Обработчик капчи"""
    key = input(f"Введите текст капчи {captcha.get_url()}: ")
    return captcha.try_again(key)

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
            print(f"[VK_AUTH] Авторизация {account} через логин/пароль...")
            vk_session = vk_api.VkApi(
                login=login,
                password=password,
                auth_handler=lambda: auth_handler(account),
                captcha_handler=captcha_handler,
                app_id=2685278,  # Kate Mobile
                scope='offline,photos,wall,groups'
            )
            vk_session.auth(token_only=False)
            _session_cache[cache_key] = vk_session
            print(f"[VK_AUTH] Авторизация {account} успешна!")
            return vk_session
        except Exception as e:
            print(f"[VK_AUTH] Ошибка авторизации через логин/пароль: {e}")
            print(f"[VK_AUTH] Пробую использовать готовый токен...")

    # Fallback: используем готовый токен
    if token:
        try:
            vk_session = vk_api.VkApi(token=token)
            _session_cache[cache_key] = vk_session
            print(f"[VK_AUTH] Использую готовый токен для {account}")
            return vk_session
        except Exception as e:
            print(f"[VK_AUTH] Ошибка с готовым токеном: {e}")

    raise Exception(
        f"Не удалось авторизоваться в VK для аккаунта '{account}'.\n"
        f"Варианты:\n"
        f"1. Укажите VK_LOGIN/VK_PASSWORD (или VK_LOGIN2/VK_PASSWORD2) в переменных окружения\n"
        f"2. Или укажите готовый VK_TOKEN/VK_TOKEN2"
    )

def get_vk_api(account='accessories'):
    """Получает VK API объект"""
    session = get_vk_session(account)
    return session.get_api()
