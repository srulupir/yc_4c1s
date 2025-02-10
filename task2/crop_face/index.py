import cv2
import boto3
import json
import os
from uuid import uuid4
import numpy as np

# Инициализация клиента S3
s3_client = boto3.client(
    "s3",
    endpoint_url="https://storage.yandexcloud.net",
    aws_access_key_id=os.getenv("YANDEX_STORAGE_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("YANDEX_STORAGE_SECRET_KEY"),
)


def save_metadata(bucket_name, face_key, metadata):
    """
    Сохраняет метаданные лица в S3.
    """
    metadata_key = face_key.replace(".jpg", ".json")
    metadata_body = json.dumps(metadata, indent=2)
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=metadata_key,
            Body=metadata_body,
            ContentType="application/json"
        )
        print(f"Метаданные успешно сохранены для ключа {metadata_key}.")
    except Exception as e:
        print(f"Ошибка при сохранении метаданных: {e}")

def crop_face(image_bytes, face_rect):
    """
    Вырезает область лица из изображения.
    """
    try:
        np_image = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(np_image, cv2.IMREAD_COLOR)

        if image is None:
            print("Ошибка: Не удалось декодировать изображение.")
            return None

        x, y, w, h = face_rect["x"], face_rect["y"], face_rect["w"], face_rect["h"]
        print(f"Вырезание лица с координатами: x={x}, y={y}, ширина={w}, высота={h}")

        face_image = image[y:y+h, x:x+w]
        _, face_bytes = cv2.imencode('.jpg', face_image)
        print(f"Размер вырезанного лица: {len(face_bytes.tobytes())} байт.")
        return face_bytes.tobytes()
    except Exception as e:
        print(f"Ошибка при вырезании лица: {e}")
        return None

def validate_face_coords(face_coords):
    """
    Проверяет, что координаты лица содержат все необходимые поля.
    """
    if not all(key in face_coords for key in ["x", "y", "w", "h"]):
        print("Ошибка: Некорректные координаты лица.")
        return False
    return True

def handler(event, context):
    """
    Обрабатывает событие, вырезает лицо из изображения и сохраняет его в S3.
    """
    for record in event['messages']:
        try:
            task = json.loads(record['details']['message']['body'])
            original_key = task["original_photo_key"]
            face_rect = task["face_rectangle"]

            if not validate_face_coords(face_rect):
                continue

            print(f"Загрузка изображения с ключом: {original_key}")
            response = s3_client.get_object(Bucket=os.getenv("IMAGES_BUCKET_NAME"), Key=original_key)
            image_bytes = response['Body'].read()

            face_bytes = crop_face(image_bytes, face_rect)
            if face_bytes is None:
                print("Ошибка: Не удалось вырезать лицо. Пропуск записи.")
                continue

            face_key = f"face_{uuid4().hex}.jpg"
            print(f"Сохранение лица с ключом: {face_key}")
            s3_client.put_object(
                Bucket=os.getenv("PROCESSED_FACES_BUCKET_NAME"),
                Key=face_key,
                Body=face_bytes,
                ContentType="image/jpeg"
            )

            metadata = {
                "original_photo_key": original_key,
                "face_key": face_key,
                "name": None
            }
            save_metadata(os.getenv("PROCESSED_FACES_BUCKET_NAME"), face_key, metadata)

        except Exception as e:
            print(f"Ошибка при обработке записи: {e}")

    return {"statusCode": 200}