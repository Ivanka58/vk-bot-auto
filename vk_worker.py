import os
import vk_api
import requests
import time
import logging

# Настройка логирования прямо в файле
logger = logging.getLogger(__name__)

def send_to_vk_groups(message_text, photo_paths, category='usual'):
    """
    Публикует пост в группы выбранной категории.
    Использует токен сообщества, хранящийся в VK_TOKEN.
    """
    print("🚀 [DEBUG] send_to_vk_groups вызвана")
    print(f"📝 [DEBUG] Текст: {message_text[:100] if message_text else 'Нет текста'}...")
    print(f"📂 [DEBUG] Категория: {category}")
    print(f"🖼️ [DEBUG] Количество фото: {len(photo_paths)}")
    print(f"🖼️ [DEBUG] Пути к фото: {photo_paths}")

    token = os.getenv("VK_TOKEN")
    print(f"🔑 [DEBUG] Токен из env: {'Получен' if token else 'НЕ ПОЛУЧЕН'}")

    if not token:
        return "❌ Ошибка: VK_TOKEN не задан"

    # Получаем списки групп из переменных окружения
    usual_raw = os.getenv("GROUPS_USUAL", "")
    large_raw = os.getenv("GROUPS_LARGE", "")
    print(f"📋 [DEBUG] GROUPS_USUAL raw: '{usual_raw}'")
    print(f"📋 [DEBUG] GROUPS_LARGE raw: '{large_raw}'")

    group_ids = []
    if category == 'usual':
        group_ids = [int(gid.strip()) for gid in usual_raw.split(",") if gid.strip()]
        print(f"📋 [DEBUG] Обычные группы (после парсинга): {group_ids}")
    else:
        group_ids = [int(gid.strip()) for gid in large_raw.split(",") if gid.strip()]
        print(f"📋 [DEBUG] Крупные группы (после парсинга): {group_ids}")

    if not group_ids:
        return f"❌ Ошибка: нет групп в категории '{category}'"

    try:
        print("🔄 [DEBUG] Создаю сессию VK...")
        vk_session = vk_api.VkApi(token=token)
        vk = vk_session.get_api()
        upload = vk_api.VkUpload(vk_session)
        print("✅ [DEBUG] Сессия VK создана")

        # Загрузка фото
        attachments = []
        for idx, path in enumerate(photo_paths):
            print(f"🖼️ [DEBUG] Обработка фото {idx+1}: {path}")
            if os.path.exists(path):
                print(f"✅ [DEBUG] Файл {path} найден, загружаю...")
                try:
                    photo = upload.photo_wall(path)[0]
                    attachments.append(f"photo{photo['owner_id']}_{photo['id']}")
                    print(f"✅ [DEBUG] Фото {idx+1} загружено: {attachments[-1]}")
                except Exception as e:
                    print(f"❌ [DEBUG] Ошибка загрузки фото {idx+1}: {e}")
            else:
                print(f"❌ [DEBUG] Файл {path} НЕ НАЙДЕН, пропускаю")
        attachments_str = ",".join(attachments)
        print(f"🖼️ [DEBUG] Итоговые вложения: {attachments_str}")

        # Публикация в каждую группу
        results = []
        for gid in group_ids:
            print(f"📤 [DEBUG] Публикую в группу {gid}...")
            try:
                vk.wall.post(owner_id=gid, message=message_text, attachments=attachments_str)
                results.append(f"✅ Группа {gid}: пост опубликован.")
                print(f"✅ [DEBUG] Успешно опубликовано в {gid}")
            except vk_api.exceptions.ApiError as e:
                error_msg = str(e)
                results.append(f"❌ Группа {gid}: ошибка VK — {error_msg[:100]}")
                print(f"❌ [DEBUG] Ошибка VK для группы {gid}: {error_msg}")
            except Exception as e:
                error_msg = str(e)
                results.append(f"❌ Группа {gid}: ошибка — {error_msg[:100]}")
                print(f"❌ [DEBUG] Общая ошибка для группы {gid}: {error_msg}")
            time.sleep(1)

        print("✅ [DEBUG] Публикация завершена")
        return "\n".join(results)

    except Exception as e:
        print(f"🔥 [DEBUG] Критическая ошибка в send_to_vk_groups: {e}")
        return f"🔥 Критическая ошибка: {e}"
