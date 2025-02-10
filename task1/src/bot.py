import boto3
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import base64
import json
import logging
import os
import asyncio
import io
from logging.config import dictConfig

# Настройка логирования
dictConfig({
    "version": 1,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default"
        }
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"]
    }
})
logger = logging.getLogger(__name__)

# Переменные окружения
TELEGRAM_API_TOKEN = os.getenv("TG_BOT_KEY")
YC_GPT_API_KEY = os.getenv("YANDEX_API_KEY")
YC_STORAGE_BUCKET = os.getenv("YC_BUCKET_NAME")
YC_PROJECT_FOLDER = os.getenv("YC_FOLDER_ID")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

# Сообщения пользователю
START_MESSAGE = (
    'Я помогу подготовить ответ на экзаменационный вопрос по дисциплине "Операционные системы".\n'
    'Пришлите мне фотографию с вопросом или введите его текстом.'
)
PHOTO_LIMIT_MESSAGE = "Я могу обработать только одну фотографию."
OCR_FAILURE_MESSAGE = "Я не могу обработать эту фотографию."
UNSUPPORTED_MESSAGE = "Я могу обработать только текстовое сообщение или фотографию."
GPT_ERROR_MESSAGE = "Я не смог подготовить ответ на экзаменационный вопрос."


def fetch_instruction_from_storage():
    try:
        session = boto3.session.Session(
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY
        )
        s3 = session.client("s3", endpoint_url="https://storage.yandexcloud.net")
        response = s3.get_object(Bucket=YC_STORAGE_BUCKET, Key="instruction.txt")
        return response['Body'].read().decode('utf-8')
    except Exception as e:
        logger.error(f"Ошибка загрузки инструкции: {e}")
        return None


def get_gpt_response(question_text):
    instruction = fetch_instruction_from_storage()
    if not instruction:
        return "Не удалось загрузить инструкцию."

    payload = {
        "modelUri": f"gpt://{YC_PROJECT_FOLDER}/yandexgpt/rc",
        "completionOptions": {"temperature": 0.5, "maxTokens": 2000},
        "messages": [
            {"role": "system", "text": instruction},
            {"role": "user", "text": question_text},
        ]
    }

    try:
        response = requests.post(
            "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            headers={
                "Accept": "application/json",
                "Authorization": f"Api-Key {YC_GPT_API_KEY}",
            },
            json=payload,
        )
        return response.json().get('result', {}).get('alternatives', [{}])[0].get('message', {}).get('text', GPT_ERROR_MESSAGE)
    except Exception as e:
        logger.error(f"Ошибка запроса к YandexGPT API: {e}")
        return GPT_ERROR_MESSAGE


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(START_MESSAGE)


async def process_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question_text = update.message.text
    logger.info(f"Запрос: {question_text}")
    response = get_gpt_response(question_text)
    await update.message.reply_text(response)


async def process_image_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.media_group_id:
        await update.message.reply_text(PHOTO_LIMIT_MESSAGE)
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()
    image_stream = io.BytesIO()
    await file.download_to_memory(image_stream)
    image_data = base64.b64encode(image_stream.getvalue()).decode("utf-8")

    ocr_payload = {"mimeType": "JPEG", "languageCodes": ["ru"], "model": "page", "content": image_data}
    try:
        response = requests.post(
            "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText",
            headers={"Authorization": f"Api-Key {YC_GPT_API_KEY}", "Content-Type": "application/json"},
            json=ocr_payload,
        )
        ocr_text = response.json().get('result', {}).get('textAnnotation', {}).get('fullText', '')
        if ocr_text:
            answer = get_gpt_response(ocr_text)
            await update.message.reply_text(answer)
        else:
            await update.message.reply_text(OCR_FAILURE_MESSAGE)
    except Exception as e:
        logger.error(f"Ошибка OCR: {e}")
        await update.message.reply_text(OCR_FAILURE_MESSAGE)


async def process_unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(UNSUPPORTED_MESSAGE)


async def handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        app = ApplicationBuilder().token(TELEGRAM_API_TOKEN).build()
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", start_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_text_message))
        app.add_handler(MessageHandler(filters.PHOTO, process_image_message))
        app.add_handler(MessageHandler(filters.ALL, process_unknown_message))

        await app.initialize()
        await app.process_update(Update.de_json(body, app.bot))
        await app.shutdown()
        return {'statusCode': 200, 'body': 'OK'}
    except Exception as e:
        logger.error(f"Ошибка обработчика: {e}")
        return {'statusCode': 500, 'body': 'Internal Server Error'}
