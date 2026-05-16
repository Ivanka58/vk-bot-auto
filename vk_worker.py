import os
import vk_api
import requests

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
        token = os.getenv('VK_TOKEN')
        groups_usual = os.getenv('GROUPS_USUAL', '')
        groups_large = os.getenv('GROUPS_LARGE', '')
    else:
        token = os.getenv('VK_TOKEN2')
        groups_usual = os.getenv('GROUPS_USUAL2', os.getenv('GROUPS_USUAL', ''))
        groups_large = os.getenv('GROUPS_LARGE2', os.getenv('GROUPS_LARGE', ''))

    if not token:
        raise Exception(f"VK_TOKEN{'2' if account != 'accessories' else ''} не найден")

    if custom_groups:
        groups = custom_groups
    else:
        groups_str = groups_usual if category == 'usual' else groups_large
        groups = [g.strip() for g in groups_str.split(',') if g.strip()]
    
    if not groups:
        raise Exception("Список групп пуст")

    print(f"[VK] Группы ({account}): {groups}")

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
            try:
                ph = upload_photo_to_wall(vk, path, gid)
                att = f"photo{ph['owner_id']}_{ph['id']}"
                attachments.append(att)
                print(f"[VK] Успех: {att}")
            except Exception as e:
                err_msg = str(e)
                print(f"[VK] ОШИБКА: {err_msg}")
                if any(x in err_msg.lower() for x in ['group auth', 'unavailable with group', 'authorization failed']):
                    raise Exception(
                        "❌ Токен сообщества (группы) НЕ МОЖЕТ загружать фото на стену ВКонтакте.\n\n"
                        "✅ Решение за 2 минуты:\n"
                        "1. Открой: https://vkhost.github.io/\n"
                        "2. Выбери 'Kate Mobile'\n"
                        "3. В поле 'scope' впиши: photos,wall\n"
                        "4. Нажми 'Получить ссылку' → разреши доступ\n"
                        "5. Скопируй access_token из адресной строки\n"
                        "6. Вставь его в Amvera в переменную VK_TOKEN"
                        f"{'2' if account != 'accessories' else ''}\n"
                        "7. Перезапусти контейнер"
                    )
                continue

        if not attachments:
            report_lines.append(f"❌ Группа {group_id}: фото не загрузились")
            continue

        attachments_str = ','.join(attachments)
        try:
            vk.wall.post(owner_id=gid, message=message_text, attachments=attachments_str)
            report_lines.append(f"✅ Группа {group_id}: пост отправлен")
            print(f"[VK] Пост ушёл")
        except Exception as e:
            report_lines.append(f"❌ Группа {group_id}: ошибка постинга — {e}")
            print(f"[VK] Ошибка постинга: {e}")

    print("=" * 60)
    
    # Формируем основной отчёт
    main_report = '\n'.join(report_lines)
    
    # Формируем дополнительную информацию
    account_name = "Аксессуары" if account == 'accessories' else "Дианы"
    category_name = "Обычные" if category == 'usual' else "Крупные"
    
    info_block = (
        f"\n\n📊 Информация об отправке:\n"
        f"👤 Отправлено через аккаунт: {account_name}\n"
        f"📁 В группы: {category_name}"
    )
    
    # Возвращаем отчёт + информацию
    full_report = main_report + info_block
    
    return full_report
