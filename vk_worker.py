import os
import vk_api
import requests

def upload_photo_to_wall(vk, path, group_id):
    """Ручная загрузка фото на стену группы через VK API."""
    gid = abs(int(group_id))
    print(f"[VK] Загрузка {path} для группы {group_id}")

    # Шаг 1: получаем сервер загрузки
    upload_data = vk.photos.getWallUploadServer(group_id=gid)
    upload_url = upload_data['upload_url']
    print(f"[VK] URL загрузки получен")

    # Шаг 2: загружаем файл на сервер ВК
    with open(path, 'rb') as f:
        response = requests.post(upload_url, files={'photo': f}, timeout=30)

    result = response.json()
    print(f"[VK] Ответ сервера загрузки: {result}")

    # Шаг 3: сохраняем фото
    saved = vk.photos.saveWallPhoto(
        group_id=gid,
        server=result['server'],
        photo=result['photo'],
        hash=result['hash']
    )

    print(f"[VK] Сохранено: {saved}")
    return saved[0]

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

    report_lines = []

    for group_id in groups:
        gid = int(group_id)
        print(f"\n[VK] --- Группа {group_id} ---")

        attachments = []
        for path in photo_paths:
            if not os.path.exists(path):
                print(f"[VK] ФАЙЛ НЕ НАЙДЕН: {path}")
                continue

            fsize = os.path.getsize(path)
            print(f"[VK] Файл: {path} ({fsize} байт)")

            try:
                ph = upload_photo_to_wall(vk, path, gid)
                att = f"photo{ph['owner_id']}_{ph['id']}"
                attachments.append(att)
                print(f"[VK] Успех: {att}")
            except Exception as e:
                err_msg = str(e)
                print(f"[VK] ОШИБКА: {err_msg}")

                # Если токен сообщества не подходит — сразу даём инструкцию
                if any(x in err_msg.lower() for x in ['group auth', 'unavailable with group', 'authorization failed']):
                    raise Exception(
                        "❌ Токен сообщества (группы) НЕ МОЖЕТ загружать фото на стену ВКонтакте.\n\n"
                        "✅ Решение за 2 минуты:\n"
                        "1. Открой: https://vkhost.github.io/\n"
                        "2. Выбери 'Kate Mobile'\n"
                        "3. В поле 'scope' впиши: photos,wall\n"
                        "4. Нажми 'Получить ссылку' → разреши доступ\n"
                        "5. Скопируй access_token из адресной строки\n"
                        "   (всё что между access_token= и &)\n"
                        "6. Вставь его в Amvera в переменную VK_TOKEN\n"
                        "   (замени старый токен сообщества)\n"
                        "7. Перезапусти контейнер"
                    )
                continue

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
            report_lines.append(f"❌ Группа {group_id}: ошибка постинга — {e}")
            print(f"[VK] Ошибка постинга: {e}")

    print("=" * 60)
    return '\n'.join(report_lines)
