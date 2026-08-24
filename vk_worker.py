import os
import vk_api
import requests
from vk_auth import get_vk_api

def upload_photo_to_wall(vk, path, group_id):
    gid = abs(int(group_id))
    print(f"[VK] Загрузка {path} для группы {group_id}")
    upload_data = vk.photos.getWallUploadServer(group_id=gid)
    upload_url = upload_data['upload_url']
    with open(path, 'rb') as f:
        response = requests.post(upload_url, files={'photo': f}, timeout=30)
    result = response.json()
    saved = vk.photos.saveWallPhoto(
        group_id=gid,
        server=result['server'],
        photo=result['photo'],
        hash=result['hash']
    )
    return saved[0]

def send_to_vk_groups(message_text, photo_paths, category='usual', account='accessories', custom_groups=None):
    print("=" * 60)
    print(f"[VK] Старт. Аккаунт: {account}")
    print(f"[VK] Фото: {len(photo_paths)} шт.")
    print(f"[VK] Текст: {message_text[:80]}...")
    print(f"[VK] Категория: {category}")

    if account == 'accessories':
        groups_usual = os.getenv('GROUPS_USUAL', '')
        groups_large = os.getenv('GROUPS_LARGE', '')
    else:
        groups_usual = os.getenv('GROUPS_USUAL2', os.getenv('GROUPS_USUAL', ''))
        groups_large = os.getenv('GROUPS_LARGE2', os.getenv('GROUPS_LARGE', ''))

    if custom_groups:
        groups = custom_groups
    else:
        groups_str = groups_usual if category == 'usual' else groups_large
        groups = [g.strip() for g in groups_str.split(',') if g.strip()]

    if not groups:
        raise Exception("Список групп пуст")

    print(f"[VK] Группы ({account}): {groups}")

    # Получаем VK API через vk_auth (автоматически по логину/паролю или готовому токену)
    vk = get_vk_api(account)

    report_lines = []

    for group_id in groups:
        gid = int(group_id)
        print(f"\n[VK] --- Группа {group_id} ---")

        attachments = []
        for path in photo_paths:
            try:
                photo = upload_photo_to_wall(vk, path, group_id)
                attachments.append(f"photo{photo['owner_id']}_{photo['id']}")
                print(f"[VK] Фото загружено: photo{photo['owner_id']}_{photo['id']}")
            except Exception as e:
                print(f"[VK] Ошибка загрузки фото: {e}")
                report_lines.append(f"❌ Группа {group_id}: ошибка загрузки фото - {e}")
                continue

        try:
            vk.wall.post(
                owner_id=-gid,
                from_group=0,
                message=message_text,
                attachments=','.join(attachments)
            )
            print(f"[VK] Успешно отправлено в группу {group_id}")
            report_lines.append(f"✅ Группа {group_id}: отправлено")
        except Exception as e:
            print(f"[VK] Ошибка отправки: {e}")
            report_lines.append(f"❌ Группа {group_id}: {e}")

    print("=" * 60)
    return "\n".join(report_lines)
