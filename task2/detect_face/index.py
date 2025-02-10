import boto3
import json
import cv2
import numpy as np
import os
import sys

# Инициализация клиентов Yandex Cloud
s3_client = boto3.client(
    "s3",
    endpoint_url="https://storage.yandexcloud.net",
    aws_access_key_id=os.getenv("YANDEX_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("YANDEX_SECRET_KEY"),
)

sqs_client = boto3.client(
    "sqs",
    endpoint_url="https://message-queue.api.cloud.yandex.net",
    aws_access_key_id=os.getenv("YANDEX_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("YANDEX_SECRET_KEY"),
    region_name="ru-central1",
)

queue_url = os.getenv("URL_QUEUE")


def extract_event_details(event: dict) -> list[dict]:
    """Разбирает входные события и возвращает список с нужными данными."""
    print("Получено новое событие. Начинаем обработку.")
    
    tasks = []
    for record in event.get("messages", []):
        event_type = record.get("event_metadata", {}).get("event_type", "unknown")
        
        if event_type != "yandex.cloud.events.storage.ObjectCreate":
            print(f"Пропущено событие неподдерживаемого типа: {event_type}")
            continue
        
        bucket = record["details"]["bucket_id"]
        key = record["details"]["object_id"]
        
        print(f"Обнаружен новый объект: {key} в бакете {bucket}. Добавляем в очередь на обработку.")
        tasks.append({"bucket": bucket, "key": key})
    
    print(f"Всего событий для обработки: {len(tasks)}")
    return tasks


def process_image(bucket: str, key: str) -> list[tuple[int, int, int, int]]:
    """Загружает изображение и выполняет детекцию лиц."""
    print(f"Начинаем загрузку изображения {key} из бакета {bucket}.")
    
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        image_data = response["Body"].read()
        print(f"Изображение {key} успешно загружено. Начинаем обработку.")
        
        # Преобразование изображения
        np_img = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Загрузка каскада для распознавания лиц
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        
        # Обнаружение лиц
        faces = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=6, minSize=(30, 30))
        print(f"На изображении {key} найдено {len(faces)} лиц.")
        
        return faces

    except Exception as e:
        print(f"Ошибка при обработке изображения {key}: {e}")
        return []


def send_task_to_queue(task: dict) -> None:
    """Отправляет задачу в очередь."""
    try:
        # Преобразуем все int32 в int, чтобы избежать ошибки сериализации
        task = json.loads(json.dumps(task, default=lambda x: int(x) if isinstance(x, np.integer) else x))
        
        response = sqs_client.send_message(QueueUrl=queue_url, MessageBody=json.dumps(task))
        print(f"Задача успешно отправлена в очередь. ID сообщения: {response['MessageId']}")
    except Exception as e:
        print(f"Ошибка при отправке задачи в очередь: {e}")


def handler(event: dict, context) -> dict:
    """Обработчик событий."""
    print("Запуск обработчика событий.")

    tasks = extract_event_details(event)

    for task in tasks:
        faces = process_image(task["bucket"], task["key"])
        
        for x, y, w, h in faces:
            message = {
                "original_photo_key": task["key"],
                "face_rectangle": {"x": x, "y": y, "w": w, "h": h},
            }
            print(f"Готовим задачу для отправки в очередь: {message}")
            send_task_to_queue(message)

    print("Обработка события завершена.")
    return {"statusCode": 200}
