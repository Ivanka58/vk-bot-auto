import os
import vk_api
import requests
import time
import logging

logger = logging.getLogger(__name__)

def send_to_vk_groups(message_text, photo_paths, category='usual'):
    """
    Публикует пост в группы выбранной категории.
    Использует токен сообщества, хранящийся в VK_TOKEN.
    """
    token = os.getenv("VK_TOKEN")
    if not token:
        return "❌ Ошибка: VK_TOKEN не задан"

    # Получаем списки групп из переменных окружения
    usual_raw = os.getenv("GROUPS_USUAL", "")
    large_raw = os.getenv("GROUPS_LARGE", "")
    group_ids = []
    if category == 'usual':
        group_ids = [int(gid.strip()) for gid in usual_raw.split(",") if gid.strip()]
    else:
        group_ids = [int(gid.strip()) for gid in large_raw.split(",") if gid.strip()]

    if not group_ids:
        return f"❌ Ошибка: нет групп в категории '{category}'"

    try:
        vk_session = vk_api.VkApi(token=token)
        vk = vk_session.get_api()
        upload = vk_api.VkUpload(vk_session)

        # Загрузка фото
        attachments = []
        for path in photo_paths:
            if os.path.exists(path):
                photo = upload.photo_wall(path)[0]
                attachments.append(f"photo{photo['owner_id']}_{photo['id']}")
        attachments_str = ",".join(attachments)

        # Публикация в каждую группу
        results = []
        for gid in group_ids:
            try:
                vk.wall.post(owner_id=gid, message=message_text, attachments=attachments_str)
                results.append(f"✅ Группа {gid}: пост опубликован.")
            except vk_api.exceptions.ApiError as e:
                results.append(f"❌ Группа {gid}: ошибка VK — {str(e)[:100]}")
            time.sleep(1)

        return "\n".join(results)
    except Exception as e:
        logger.error(f"Критическая ошибка публикации: {e}")
        return f"🔥 Критическая ошибка: {e}"
