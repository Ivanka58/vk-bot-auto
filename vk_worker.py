import os
import vk_api
from vk_api.upload import VkUpload

def send_to_vk_groups(message_text, photo_paths, category='usual'):
    """
    Загружает фото и публикует пост в предложку групп ВК.
    Возвращает многострочный отчёт.
    """
    print("=" * 60)
    print("[VK] Начало отправки")

    token = os.getenv('VK_TOKEN')
    groups_usual = os.getenv('GROUPS_USUAL', '')
    groups_large = os.getenv('GROUPS_LARGE', '')

    if not token:
        raise Exception("VK_TOKEN не найден в переменных окружения")

    groups_str = groups_usual if category == 'usual' else groups_large
    if not groups_str:
        raise Exception(f"GROUPS_{category.upper()} не заданы в .env")

    groups = [g.strip() for g in groups_str.split(',') if g.strip()]
    print(f"[VK] ID групп ({category}): {groups}")

    # Инициализация сессии
    vk_session = vk_api.VkApi(token=token)
    vk = vk_session.get_api()
    upload = VkUpload(vk_session)

    # ─── Загрузка фото ───
    attachments = []
    print(f"[VK] Загрузка {len(photo_paths)} фото...")

    for path in photo_paths:
        if not os.path.exists(path):
            print(f"[VK] ⚠️ Файл не существует: {path}")
            continue

        try:
            photo = upload.photo_wall(path)
            owner_id = photo[0]['owner_id']
            photo_id = photo[0]['id']
            attachments.append(f"photo{owner_id}_{photo_id}")
            print(f"[VK] ✅ Фото загружено: photo{owner_id}_{photo_id}")
        except Exception as e:
            print(f"[VK] ❌ Ошибка загрузки фото {path}: {e}")

    if not attachments:
        raise Exception("Не удалось загрузить ни одного фото")

    attachments_str = ','.join(attachments)
    print(f"[VK] Итоговые вложения: {attachments_str}")

    # ─── Постинг в группы ───
    report_lines = []

    for group_id in groups:
        try:
            print(f"[VK] Отправка в группу {group_id}...")
            # owner_id со знаком минус → пост уходит в предложку группы
            vk.wall.post(
                owner_id=int(group_id),
                message=message_text,
                attachments=attachments_str
            )
            report_lines.append(f"✅ Группа {group_id}: пост опубликован.")
            print(f"[VK] ✅ Успешно: {group_id}")
        except Exception as e:
            err = str(e)
            report_lines.append(f"❌ Группа {group_id}: ошибка — {err}")
            print(f"[VK] ❌ Ошибка в {group_id}: {err}")

    print("[VK] Отправка завершена")
    print("=" * 60)
    return '\n'.join(report_lines)