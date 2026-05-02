import os
import vk_api
import requests
import time
import logging

logger = logging.getLogger(__name__)

def send_to_vk_groups(message_text, photo_paths):
    """
    Отправляет пост во все группы из переменных окружения.
    - GROUPS_USUAL и GROUPS_LARGE — списки ID групп через запятую (с минусом, например -12345678)
    - VK_TOKEN — токен сообщества
    """
    usual_raw = os.getenv("GROUPS_USUAL", "")
    large_raw = os.getenv("GROUPS_LARGE", "")
    
    group_ids = []
    if usual_raw:
        group_ids.extend([int(gid.strip()) for gid in usual_raw.split(",") if gid.strip()])
    if large_raw:
        group_ids.extend([int(gid.strip()) for gid in large_raw.split(",") if gid.strip()])

    token = os.getenv("VK_TOKEN")

    if not token:
        return "❌ Нет VK_TOKEN"
    if not group_ids:
        return "❌ Нет групп для отправки"

    try:
        vk_session = vk_api.VkApi(token=token)
        vk = vk_session.get_api()
        upload = vk_api.VkUpload(vk_session)

        # Загрузка фото
        attachments = []
        for path in photo_paths:
            if not os.path.exists(path):
                continue
            photo = upload.photo_wall(path)[0]
            attachments.append(f"photo{photo['owner_id']}_{photo['id']}")
        attachments_str = ",".join(attachments)

        results = []
        for gid in group_ids:
            try:
                vk.wall.post(owner_id=gid, message=message_text, attachments=attachments_str)
                results.append(f"✅ Группа {gid}: пост опубликован")
                logger.info(f"Пост в {gid} отправлен")
            except vk_api.exceptions.ApiError as e:
                err = str(e)
                results.append(f"❌ Группа {gid}: ошибка — {err[:100]}")
                logger.error(f"Ошибка в группе {gid}: {err}")
            time.sleep(1)

        return "\n".join(results)

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        return f"🔥 Критическая ошибка: {e}"
