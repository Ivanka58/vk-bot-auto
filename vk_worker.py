import os
import vk_api
from vk_api.upload import VkUpload

def send_to_vk_groups(message_text, photo_paths, category='usual'):
    print("=" * 60)
    print(f"[VK] Старт. Фото: {photo_paths}")
    print(f"[VK] Текст: {message_text[:80]}...")
    print(f"[VK] Категория: {category}")

    token = os.getenv('VK_TOKEN')
    groups_usual = os.getenv('GROUPS_USUAL', '')
    groups_large = os.getenv('GROUPS_LARGE', '')

    if not token:
        raise Exception("VK_TOKEN не найден")

    groups_str = groups_usual if category == 'usual' else groups_large
    if not groups_str:
        raise Exception(f"GROUPS_{category.upper()} пусты")

    groups = [g.strip() for g in groups_str.split(',') if g.strip()]
    print(f"[VK] Группы: {groups}")

    vk_session = vk_api.VkApi(token=token)
    vk = vk_session.get_api()
    upload = VkUpload(vk_session)

    report_lines = []

    for group_id in groups:
        gid = int(group_id)
        print(f"\n[VK] --- Группа {group_id} ---")

        # Загружаем фото СПЕЦИАЛЬНО для этой группы (обязательно для токена сообщества)
        attachments = []
        for path in photo_paths:
            if not os.path.exists(path):
                print(f"[VK] ФАЙЛ НЕ НАЙДЕН: {path}")
                continue

            fsize = os.path.getsize(path)
            print(f"[VK] Загрузка: {path} ({fsize} байт)")

            try:
                # abs(gid) — group_id для загрузки должен быть БЕЗ минуса
                result = upload.photo_wall(path, group_id=abs(gid))
                print(f"[VK] Ответ сервера: {result}")

                if result and len(result) > 0:
                    ph = result[0]
                    att = f"photo{ph['owner_id']}_{ph['id']}"
                    attachments.append(att)
                    print(f"[VK] Успех: {att}")
                else:
                    print(f"[VK] Пустой ответ от сервера при загрузке {path}")
            except Exception as e:
                print(f"[VK] ОШИБКА загрузки {path}: {e}")

        if not attachments:
            report_lines.append(f"❌ Группа {group_id}: фото не загрузились")
            continue

        attachments_str = ','.join(attachments)
        print(f"[VK] Вложения: {attachments_str}")

        try:
            vk.wall.post(owner_id=gid, message=message_text, attachments=attachments_str)
            report_lines.append(f"✅ Группа {group_id}: пост отправлен")
            print(f"[VK] Пост ушёл")
        except Exception as e:
            report_lines.append(f"❌ Группа {group_id}: ошибка — {e}")
            print(f"[VK] Ошибка постинга: {e}")

    print("=" * 60)
    return '\n'.join(report_lines)
