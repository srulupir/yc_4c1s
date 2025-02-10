from uuid import uuid4
import boto3
import os
import json
import requests

PROCESSED_FACES_BUCKET_NAME = os.getenv("PROCESSED_FACES_BUCKET_NAME")
IMAGES_BUCKET_NAME = os.getenv("IMAGES_BUCKET_NAME")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"
YANDEX_STORAGE_ACCESS_KEY = os.getenv("YANDEX_STORAGE_ACCESS_KEY")
YANDEX_STORAGE_SECRET_KEY = os.getenv("YANDEX_STORAGE_SECRET_KEY")
API_GATEWAY = os.getenv("API_GATEWAY")
API_GATEWAY_ORIGINAL = os.getenv("API_GATEWAY_ORIGINAL")

# Инициализация клиента для S3
s3_client = boto3.client(
    "s3",
    endpoint_url="https://storage.yandexcloud.net",
    aws_access_key_id=YANDEX_STORAGE_ACCESS_KEY,
    aws_secret_access_key=YANDEX_STORAGE_SECRET_KEY,
)

user_sessions = {}

def get_unnamed_face():
    response = s3_client.list_objects_v2(Bucket=PROCESSED_FACES_BUCKET_NAME)
    if "Contents" not in response:
        return None, None

    for obj in response["Contents"]:
        if obj["Key"].endswith(".json"):
            metadata = s3_client.get_object(Bucket=PROCESSED_FACES_BUCKET_NAME, Key=obj["Key"])
            metadata = json.loads(metadata["Body"].read().decode("utf-8"))
            if metadata.get("name") is None:
                return metadata["face_key"], obj["Key"]

    return None, None

def get_face(chat_id):
    face_key, metadata_key = get_unnamed_face()
    if not face_key:
        send_message(chat_id, "Нет фотографий без имени.")
        return

    face_url = f"{API_GATEWAY}/?face={face_key}"
    send_photo(chat_id, face_url)

    user_sessions[chat_id] = {"metadata_key": metadata_key, "face_url": face_url}

    # Логируем перед сохранением
    print(f"Сохранение имени для фотографии: {metadata_key}")  # Логируем metadata_key
    metadata = s3_client.get_object(Bucket=PROCESSED_FACES_BUCKET_NAME, Key=metadata_key)
    metadata = json.loads(metadata["Body"].read().decode("utf-8"))
    print(f"Метаданные фотографии перед изменением: {metadata}")  # Логируем метаданные

def find_photo(chat_id, name):
    print(f"получена команда /find с текстом - {name}")  # Лог входного параметра

    if not name:
        print("Ошибка: имя не передано!")  # Лог ошибки
        send_message(chat_id, "Введите имя для поиска.")
        return

    print(f"Начинаем поиск фотографий для имени: {name}")  # Лог перед поиском
    found_photos = search_original_photos_by_name(name)
    
    if found_photos is None:
        print(f"Ошибка: функция search_original_photos_by_name вернула None для имени {name}")  # Лог ошибки
        send_message(chat_id, "Произошла ошибка при поиске фотографий.")
        return

    if not found_photos:
        print(f"Фотографии с именем {name} не найдены.")  # Лог отсутствия результатов
        send_message(chat_id, f"Фотографии с именем {name} не найдены.")
        return

    print(f"Найдено {len(found_photos)} фотографий для имени {name}")  # Лог количества найденных фото
    for photo_key in found_photos:
        photo_url = f"{API_GATEWAY_ORIGINAL}/?image={photo_key}"
        print(f"Отправляем фото: {photo_url}")  # Лог отправки фото
        send_photo(chat_id, photo_url)

def send_message(chat_id, text):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        response = requests.post(url, json=payload)
        print(f"Ответ Telegram API: {response.status_code}, {response.text}")  # Логируем ответ
    except Exception as e:
        print(f"Ошибка отправки сообщения: {e}")

def send_photo(chat_id, photo_url):
    url = f"{TELEGRAM_API_URL}/sendPhoto"
    payload = {"chat_id": chat_id, "photo": photo_url}
    try:
        response = requests.post(url, json=payload)
        print(f"Ответ отправки фото: {response.status_code}")  # Логируем ответ
    except Exception as e:
        print(f"Ошибка отправки фото: {e}")

def handle_text_input(chat_id, text):
    if chat_id not in user_sessions or "metadata_key" not in user_sessions[chat_id]:
        send_message(chat_id, "Ошибка.")
        return

    metadata_key = user_sessions[chat_id]["metadata_key"]
    update_face_name(metadata_key, text)

    send_message(chat_id, f"Имя '{text}' сохранено для фотографии.")
    del user_sessions[chat_id]

def sending_photo_error(message, chat_id):
    send_message(chat_id, "Отправка фотографий в данный момент не поддерживается.")

def update_face_name(metadata_key, name):
    response = s3_client.get_object(Bucket=PROCESSED_FACES_BUCKET_NAME, Key=metadata_key)
    metadata = json.loads(response["Body"].read().decode("utf-8"))
    print(f"Перед сохранением: {metadata}")  # Логируем метаданные до изменения
    metadata["name"] = name
    store_metadata(metadata["face_key"], metadata)
    print(f"Метаданные после обновления: {metadata}")  # Логируем после изменения

def store_metadata(face_key, metadata):
    if "name" not in metadata or not metadata["name"]:
        print(f"Ошибка! Имя пустое для фотографии с ключом {face_key}")
    else:
        metadata_key = face_key.replace(".jpg", ".json")
        metadata_body = json.dumps(metadata, indent=2)
        s3_client.put_object(
            Bucket=PROCESSED_FACES_BUCKET_NAME,
            Key=metadata_key,
            Body=metadata_body,
            ContentType="application/json"
        )
        print(f"Метаданные успешно сохранены для фотографии с ключом {face_key}")

def search_original_photos_by_name(name):
    print(f"Поиск фотографий с именем: {name}")  # Логируем запрос
    response = s3_client.list_objects_v2(Bucket=PROCESSED_FACES_BUCKET_NAME)
    original_photos = []

    for obj in response.get("Contents", []):
        if obj["Key"].endswith(".json"):
            metadata = s3_client.get_object(Bucket=PROCESSED_FACES_BUCKET_NAME, Key=obj["Key"])
            metadata = json.loads(metadata["Body"].read().decode("utf-8"))
            if metadata.get("name") == name:
                response_ph = s3_client.list_objects_v2(Bucket=IMAGES_BUCKET_NAME)
                for obj_ph in response_ph.get("Contents", []):
                    if obj_ph["Key"].endswith(".jpg") and metadata["original_photo_key"] == obj_ph["Key"]:
                        original_photos.append(metadata["original_photo_key"])

    print(f"Найдено {len(original_photos)} фотографий.")  # Логируем количество найденных
    print(f"📸 Найденные фото (ключи): {original_photos}")
    return original_photos

def handler(event, context):
    try:
        data = json.loads(event.get('body'))
    except Exception as e:
        print(f"Ошибка чтения JSON: {e}")
        return {"statusCode": 400, "body": f"Invalid JSON: {e}"}
    
    if "message" not in data:
        return {"statusCode": 200, "body": "No message in update"}

    message = data["message"]
    chat_id = message["chat"]["id"]

    if "text" in message:
        text = message["text"]

        if text == "/start":
            send_message(chat_id, "Команды:\n/getface - получить фото лица\n/find {name} - найти фото по имени")
        elif text == "/getface":
            get_face(chat_id)
        elif text.startswith("/find"):
            find_photo(chat_id, text[6:].strip())
        else:
            handle_text_input(chat_id, text)

    elif "photo" in message:
        sending_photo_error(message, chat_id)

    return {"statusCode": 200, "body": "OK"}