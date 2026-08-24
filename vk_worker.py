import os
import requests
from vk_auth import get_vk_api

def upload_photo_to_wall(api, path, group_id):
    gid = abs(int(group_id))
    print(f"[VK] Загрузка {path} для группы {group_id}")

    # Получаем сервер для загрузки на стену
    upload_data = api.photos.getWallUploadServer(group_id=gid)
    upload_url = upload_data['upload_url']

    with open(path, 'rb') as f:
        response = requests.post(upload_url, files={'photo': f}, timeout=30)
    result = response.json()

    # Сохраняем фото на стену
    saved = api.photos.saveWallPhoto(
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

    # Получаем VK API через прямую авторизацию
    api = get_vk_api(account)

    report_lines = []
    error_count = 0
    success_count = 0

    for group_id in groups:
        gid = int(group_id)
        print(f"\n[VK] --- Группа {group_id} ---")

        attachments = []
        photo_error = None
        for path in photo_paths:
            try:
                photo = upload_photo_to_wall(api, path, group_id)
                attachments.append(f"photo{photo['owner_id']}_{photo['id']}")
                print(f"[VK] Фото загружено: photo{photo['owner_id']}_{photo['id']}")
            except Exception as e:
                photo_error = str(e)
                print(f"[VK] Ошибка загрузки фото: {e}")
                break

        if photo_error:
            error_count += 1
            short_error = photo_error[:100] + "..." if len(photo_error) > 100 else photo_error
            report_lines.append(f"❌ Гр. {group_id}: {short_error}")
            if "invalid access_token" in photo_error or "authorization failed" in photo_error:
                break
            continue

        try:
            api.wall.post(
                owner_id=-gid,
                from_group=0,
                message=message_text,
                attachments=','.join(attachments)
            )
            print(f"[VK] Успешно отправлено в группу {group_id}")
            success_count += 1
            report_lines.append(f"✅ Гр. {group_id}: ок")
        except Exception as e:
            error_count += 1
            short_error = str(e)[:100] + "..." if len(str(e)) > 100 else str(e)
            print(f"[VK] Ошибка отправки: {e}")
            report_lines.append(f"❌ Гр. {group_id}: {short_error}")

    print("=" * 60)

    header = f"📊 Отчет: ✅ {success_count} | ❌ {error_count} | Всего: {len(groups)}\n\n"
    report_text = "\n".join(report_lines)

    max_len = 3800
    if len(report_text) > max_len:
        report_text = report_text[:max_len] + "\n... (обрезано)"

    return header + report_text