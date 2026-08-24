import os
import vk
from dotenv import load_dotenv

load_dotenv()

_api_cache = {}

def get_vk_api(account='accessories'):
    """
    Получает VK API через прямую авторизацию (DirectUserAPI).
    Использует логин/пароль напрямую, минуя OAuth-страницы.
    """
    global _api_cache

    if account in _api_cache:
        return _api_cache[account]

    if account == 'accessories':
        login = os.getenv('VK_LOGIN')
        password = os.getenv('VK_PASSWORD')
    else:
        login = os.getenv('VK_LOGIN2')
        password = os.getenv('VK_PASSWORD2')

    if not login or not password:
        raise Exception(
            f"Не указаны логин/пароль для аккаунта '{account}'.\n"
            f"Добавьте в переменные окружения:\n"
            f"VK_LOGIN / VK_PASSWORD (или VK_LOGIN2 / VK_PASSWORD2)"
        )

    print(f"[VK_AUTH] Авторизация {account} через DirectUserAPI ({login})...")

    try:
        # DirectUserAPI - прямая авторизация через официальные client_id Android-приложения VK
        api = vk.DirectUserAPI(
            user_login=login,
            user_password=password,
            client_id=2274003,           # VK Android app ID
            client_secret='hHbZxrka2uZ6jB1inYsH',
            scope='offline,photos,wall,groups',
            v='5.199'
        )

        # Проверяем что авторизация прошла
        me = api.users.get()[0]
        print(f"[VK_AUTH] Успешно! Пользователь: {me['first_name']} {me['last_name']} (id{me['id']})")

        _api_cache[account] = api
        return api

    except Exception as e:
        print(f"[VK_AUTH] Ошибка DirectUserAPI: {e}")
        raise Exception(
            f"Не удалось авторизоваться в VK для '{account}'.\n"
            f"Ошибка: {e}\n\n"
            f"Возможные причины:\n"
            f"1. Неверный логин/пароль\n"
            f"2. VK требует подтверждение входа (проверьте уведомления в приложении VK)\n"
            f"3. Аккаунт временно заблокирован для API-доступа"
        )