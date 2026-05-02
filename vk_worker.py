import os
import vk_api
from vk_api.upload import VkUpload

def upload_photos_for_group(vk_session, upload, photo_paths, group_id=None):
    """Загружает фото и возвращает список attachments."""
    attachments = []
    
    for path in photo_paths:
        if not os.path.exists(path):
            print(f"[VK] ⚠️ Файл не существует: {path}")
            continue
            
        file_size = os.path.getsize(path)
        print(f"[VK] Файл найден: {path} | Размер: {file_size} байт")
        
        try:
            if group_id:
                # Для токена СООБЩЕСТВА: загружаем в конкретную группу
                print(f"[VK] Загрузка с group_id={group_id} (токен сообщества)...")
                photo = upload.photo_wall(path, group_id=abs(int(group_id)))
            else:
                # Для токена ПОЛЬЗОВАТЕЛЯ: загружаем на стену пользователя
                print(f"[VK] Загрузка без group_id (токен пользователя)...")
                photo = upload.photo_wall(path)
                
            owner_id = photo[0]['owner_id']
            photo_id = photo[0]['id']
            attachments.append(f"photo{owner_id}_{photo_id}")
            print(f"[VK] ✅ Фото загружено: photo{owner_id}_{photo_id}")
        except Exception as e:
            print(f"[VK] ❌ Ошибка загрузки фото {path}: {e}")
            continue
            
    return attachments

def send_to_vk_groups(message_text, photo_paths, category='usual'):
    print("=" * 60)
    print("[VK] Начало отправки")
    print(f"[VK] Получено фото: {photo_paths}")
    print(f"[VK] Текст: {message_text[:100]}...")
    print(f"[VK] Категория: {category}")

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

    vk_session = vk_api.VkApi(token=token)
    vk = vk_session.get_api()
    upload = VkUpload(vk_session)

    # Пробуем загрузить фото без group_id (для пользовательского токена)
    print("[VK] Попытка глобальной загрузки фото (пользовательский токен)...")
    attachments = upload_photos_for_group(vk_session, upload, photo_paths, group_id=None)
    
    # Если не получилось — будем грузить отдельно для каждой группы (токен сообщества)
    use_per_group_upload = False
    if not attachments and photo_paths:
        print("[VK] ⚠️ Глобальная загрузка не сработала. Переключаемся на групповую загрузку (токен сообщества)...")
        use_per_group_upload = True

    report_lines = []

    for group_id in groups:
        try:
            gid = int(group_id)
            print(f"[VK] --- Обработка группы {group_id} ---")
            
            current_attachments = attachments
            
            # Если фото не загружены глобально — загружаем специально для этой группы
            if use_per_group_upload and photo_paths:
                print(f"[VK] Загрузка фото специально для группы {group_id}...")
                current_attachments = upload_photos_for_group(
                    vk_session, upload, photo_paths, group_id=abs(gid)
                )
                if not current_attachments:
                    raise Exception("Не удалось загрузить фото для этой группы")
            
            attachments_str = ','.join(current_attachments) if current_attachments else ''
            print(f"[VK] Вложения для группы {group_id}: {attachments_str}")
            
            vk.wall.post(
                owner_id=gid,
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