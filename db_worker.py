import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

# Fallback: in-memory storage если БД недоступна
_in_memory_ads = {}
_next_id = 1

def _get_next_id():
    global _next_id
    _next_id += 1
    return _next_id - 1

def get_conn():
    """Создаёт подключение к Postgres через DATABASE_URL"""
    if not DATABASE_URL:
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    except Exception as e:
        print(f"[DB] Ошибка подключения: {e}")
        return None

def _safe_json_loads(value):
    """Безопасно парсит JSON — если уже объект, возвращает как есть"""
    if value is None:
        return [] if isinstance(value, list) else {}
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except:
            return [] if value.startswith('[') else {}
    return value

def init_db():
    """Создаёт таблицу если её нет"""
    conn = get_conn()
    if not conn:
        print("[DB] DATABASE_URL не настроен. Работаем в памяти.")
        return False

    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_ads (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    text TEXT NOT NULL,
                    photos JSONB NOT NULL DEFAULT '[]',
                    category TEXT NOT NULL DEFAULT 'usual',
                    account TEXT NOT NULL DEFAULT 'accessories',
                    days JSONB NOT NULL DEFAULT '[]',
                    time TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_sent JSONB NOT NULL DEFAULT '{}'
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_scheduled_ads_chat_id 
                ON scheduled_ads(chat_id);
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_scheduled_ads_time 
                ON scheduled_ads(time);
            """)
            conn.commit()
        print("[DB] Таблица scheduled_ads готова")
        return True
    except Exception as e:
        print(f"[DB] Ошибка инициализации: {e}")
        return False
    finally:
        conn.close()

def save_scheduled_ad(chat_id, text, photos, category, account, days, time):
    """Сохраняет запланированное объявление"""
    conn = get_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO scheduled_ads (chat_id, text, photos, category, account, days, time, created_at, last_sent)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (chat_id, text, json.dumps(photos), category, account, json.dumps(days), time, datetime.now(timezone.utc).isoformat(), json.dumps({})))
                result = cur.fetchone()
                conn.commit()
                return result[0]
        except Exception as e:
            print(f"[DB] Ошибка сохранения: {e}")
        finally:
            conn.close()

    ad_id = _get_next_id()
    _in_memory_ads[ad_id] = {
        'chat_id': chat_id,
        'text': text,
        'photos': photos,
        'category': category,
        'account': account,
        'days': days,
        'time': time,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'last_sent': {}
    }
    return ad_id

def get_scheduled_ads(chat_id):
    """Получает все запланированные объявления пользователя"""
    conn = get_conn()
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM scheduled_ads WHERE chat_id = %s ORDER BY id;
                """, (chat_id,))
                rows = cur.fetchall()
                ads = []
                for row in rows:
                    ads.append({
                        'id': row['id'],
                        'chat_id': row['chat_id'],
                        'text': row['text'],
                        'photos': _safe_json_loads(row['photos']),
                        'category': row['category'],
                        'account': row['account'],
                        'days': _safe_json_loads(row['days']),
                        'time': row['time'],
                        'created_at': row['created_at'],
                        'last_sent': _safe_json_loads(row['last_sent'])
                    })
                return ads
        except Exception as e:
            print(f"[DB] Ошибка получения списка: {e}")
        finally:
            conn.close()

    ads = []
    for ad_id, ad in _in_memory_ads.items():
        if ad['chat_id'] == chat_id:
            ad_copy = dict(ad)
            ad_copy['id'] = ad_id
            ads.append(ad_copy)
    return ads

def get_scheduled_ad_by_id(ad_id):
    """Получает объявление по ID"""
    conn = get_conn()
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM scheduled_ads WHERE id = %s;
                """, (ad_id,))
                row = cur.fetchone()
                if row:
                    return {
                        'id': row['id'],
                        'chat_id': row['chat_id'],
                        'text': row['text'],
                        'photos': _safe_json_loads(row['photos']),
                        'category': row['category'],
                        'account': row['account'],
                        'days': _safe_json_loads(row['days']),
                        'time': row['time'],
                        'created_at': row['created_at'],
                        'last_sent': _safe_json_loads(row['last_sent'])
                    }
        except Exception as e:
            print(f"[DB] Ошибка получения объявления: {e}")
        finally:
            conn.close()

    if ad_id in _in_memory_ads:
        ad_copy = dict(_in_memory_ads[ad_id])
        ad_copy['id'] = ad_id
        return ad_copy
    return None

def delete_scheduled_ad(ad_id):
    """Удаляет запланированное объявление"""
    conn = get_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM scheduled_ads WHERE id = %s;", (ad_id,))
                conn.commit()
                return True
        except Exception as e:
            print(f"[DB] Ошибка удаления: {e}")
        finally:
            conn.close()

    if ad_id in _in_memory_ads:
        del _in_memory_ads[ad_id]
        return True
    return False

def update_scheduled_ad(ad_id, updates):
    """Обновляет запланированное объявление"""
    if not updates:
        return True

    conn = get_conn()
    if conn:
        try:
            set_parts = []
            values = []
            for key, value in updates.items():
                if key in ['photos', 'days', 'last_sent']:
                    set_parts.append(f"{key} = %s")
                    values.append(json.dumps(value))
                else:
                    set_parts.append(f"{key} = %s")
                    values.append(value)

            values.append(ad_id)
            query = f"UPDATE scheduled_ads SET {', '.join(set_parts)} WHERE id = %s;"

            with conn.cursor() as cur:
                cur.execute(query, values)
                conn.commit()
                return True
        except Exception as e:
            print(f"[DB] Ошибка обновления: {e}")
        finally:
            conn.close()

    if ad_id in _in_memory_ads:
        _in_memory_ads[ad_id].update(updates)
        return True
    return False

def check_time_conflict(chat_id, days, time_str, exclude_id=None):
    """Проверяет, есть ли конфликт по времени с другими объявлениями"""
    ads = get_scheduled_ads(chat_id)
    for ad in ads:
        if exclude_id and ad['id'] == exclude_id:
            continue
        if ad['time'] == time_str:
            for day in days:
                if day in ad['days']:
                    return True
    return False

def get_due_ads(day_code, time_str):
    """Получает объявления, которые нужно отправить сейчас"""
    conn = get_conn()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM scheduled_ads;")
                rows = cur.fetchall()
                due = []
                for row in rows:
                    days = _safe_json_loads(row['days'])
                    if day_code in days and row['time'] == time_str:
                        last_sent = _safe_json_loads(row['last_sent'])
                        if last_sent.get(day_code) != today:
                            due.append({
                                'id': row['id'],
                                'chat_id': row['chat_id'],
                                'text': row['text'],
                                'photos': _safe_json_loads(row['photos']),
                                'category': row['category'],
                                'account': row['account'],
                                'days': days,
                                'time': row['time']
                            })
                return due
        except Exception as e:
            print(f"[DB] Ошибка получения due ads: {e}")
        finally:
            conn.close()

    due = []
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    for ad_id, ad in _in_memory_ads.items():
        if day_code in ad['days'] and ad['time'] == time_str:
            last_sent = ad.get('last_sent', {})
            if last_sent.get(day_code) != today:
                ad_copy = dict(ad)
                ad_copy['id'] = ad_id
                due.append(ad_copy)
    return due

def mark_ad_sent(ad_id, day_code):
    """Отмечает объявление как отправленное на сегодня для указанного дня"""
    ad = get_scheduled_ad_by_id(ad_id)
    if not ad:
        return

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    last_sent = ad.get('last_sent', {})
    last_sent[day_code] = today

    update_scheduled_ad(ad_id, {'last_sent': last_sent})
