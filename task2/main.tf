terraform {
  required_providers {
    yandex = {
      source = "yandex-cloud/yandex"
    }
  }
  required_version = ">= 0.13"
}

resource "yandex_iam_service_account_static_access_key" "sa_key" {
  service_account_id = var.service_account_id
}

provider "yandex" {
  service_account_key_file = "C:/Users/tatya/.yc-keys/key.json"
  cloud_id                 = var.cloud_id
  folder_id                = var.folder_id
}

resource "yandex_storage_bucket" "images" {
  bucket     = var.images_bucket_name
  access_key = yandex_iam_service_account_static_access_key.sa_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa_key.secret_key
  acl        = "private"
}

resource "yandex_storage_bucket" "processed_faces" {
  bucket     = var.processed_faces_bucket_name
  access_key = yandex_iam_service_account_static_access_key.sa_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa_key.secret_key
  acl        = "private"
}

resource "yandex_message_queue" "processing_queue" {
  name       = var.processing_queue_name
  access_key = yandex_iam_service_account_static_access_key.sa_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa_key.secret_key
}

resource "yandex_api_gateway" "api_gateway" {
  name = var.api_gateway_name
  spec = <<EOF
openapi: "3.0.0"
info:
  version: 1.0.0
  title: Face Image API
paths:
  /:
    get:
      summary: Get face image
      operationId: getFaceImage
      parameters:
        - name: face
          in: query
          description: User face
          required: true
          schema:
            type: string
            default: 'face'
      x-yc-apigateway-integration:
        type: object_storage
        bucket: ${var.processed_faces_bucket_name}
        service_account_id: ${var.service_account_id}
        object: '{face}'
  EOF
}

resource "yandex_api_gateway" "api_gateway_original" {
  name = var.api_gateway_original_name
  spec = <<EOF
openapi: "3.0.0"
info:
  version: 1.0.0
  title: Image API
paths:
  /:
    get:
      summary: Get original image
      operationId: getImage
      parameters:
        - name: image
          in: query
          description: User image
          required: true
          schema:
            type: string
            default: 'image'
      x-yc-apigateway-integration:
        type: object_storage
        bucket: ${var.images_bucket_name}
        service_account_id: ${var.service_account_id}
        object: '{image}'
  EOF
}

resource "yandex_function" "tg_bot_func" {
  name               = var.tg_bot_func_name
  user_hash          = "v2"
  runtime            = "python312"
  entrypoint         = "index.handler"
  memory             = "128"
  execution_timeout  = "50"
  service_account_id = var.service_account_id
  environment = {
    FOLDER_ID                   = var.folder_id
    TG_BOT_TOKEN                = var.telegram_bot_token
    API_GATEWAY                 = yandex_api_gateway.api_gateway.domain
    YANDEX_STORAGE_ACCESS_KEY   = yandex_iam_service_account_static_access_key.sa_key.access_key
    YANDEX_STORAGE_SECRET_KEY   = yandex_iam_service_account_static_access_key.sa_key.secret_key
    API_GATEWAY_ORIGINAL        = yandex_api_gateway.api_gateway_original.domain
    IMAGES_BUCKET_NAME          = var.images_bucket_name
    PROCESSED_FACES_BUCKET_NAME = var.processed_faces_bucket_name
  }
  content {
    zip_filename = archive_file.zip1.output_path
  }
  depends_on = [yandex_api_gateway.api_gateway, yandex_api_gateway.api_gateway_original]
}

resource "yandex_function" "detect_face_func" {
  name               = var.detect_face_func_name
  user_hash          = "v2"
  runtime            = "python312"
  entrypoint         = "index.handler"
  memory             = "128"
  execution_timeout  = "5"
  service_account_id = var.service_account_id
  environment = {
    YANDEX_ACCESS_KEY = yandex_iam_service_account_static_access_key.sa_key.access_key
    YANDEX_SECRET_KEY = yandex_iam_service_account_static_access_key.sa_key.secret_key
    URL_QUEUE         = yandex_message_queue.processing_queue.id
  }
  content {
    zip_filename = archive_file.zip3.output_path
  }
}

resource "yandex_function" "crop_face_func" {
  name               = var.crop_face_func_name
  user_hash          = "v2"
  runtime            = "python312"
  entrypoint         = "index.handler"
  memory             = "128"
  execution_timeout  = "5"
  service_account_id = var.service_account_id
  environment = {
    YANDEX_STORAGE_ACCESS_KEY   = yandex_iam_service_account_static_access_key.sa_key.access_key
    YANDEX_STORAGE_SECRET_KEY   = yandex_iam_service_account_static_access_key.sa_key.secret_key
    IMAGES_BUCKET_NAME          = var.images_bucket_name
    PROCESSED_FACES_BUCKET_NAME = var.processed_faces_bucket_name
  }
  content {
    zip_filename = archive_file.zip2.output_path
  }
}

resource "yandex_function_iam_binding" "function-iam" {
  function_id = yandex_function.tg_bot_func.id
  role        = "functions.functionInvoker"
  members     = ["system:allUsers", ]
  depends_on  = [yandex_function.tg_bot_func]
}

resource "yandex_function_trigger" "image_upload_trigger" {
  name = var.image_upload_trigger_name

  object_storage {
    bucket_id    = yandex_storage_bucket.images.id
    suffix       = ".jpg"
    create       = true
    batch_cutoff = 60
  }

  function {
    id                 = yandex_function.detect_face_func.id
    service_account_id = var.service_account_id
    tag                = "$latest"
  }
}

resource "yandex_function_trigger" "queue_trigger" {
  name = var.queue_trigger_name
  message_queue {
    queue_id           = yandex_message_queue.processing_queue.arn
    batch_cutoff       = 60
    service_account_id = var.service_account_id
    batch_size         = 1000
  }

  function {
    id                 = yandex_function.crop_face_func.id
    service_account_id = var.service_account_id
    tag                = "$latest"
  }
}

provider "null" {}

resource "null_resource" "register_webhook" {
  provisioner "local-exec" {
    when    = create
    command = <<EOT
curl -X POST https://api.telegram.org/bot${var.telegram_bot_token}/setWebhook?url=${var.webhook_url}${yandex_function.tg_bot_func.id}
EOT
  }
  depends_on = [yandex_function.tg_bot_func]
}


/*
resource "null_resource" "delete_webhook" {
  provisioner "local-exec" {
    when = destroy
    command = <<EOT
curl -X POST https://api.telegram.org/bot${var.telegram_bot_token}/deleteWebhook
EOT
  }
  depends_on = [yandex_function.tg_bot_func]
}
*/


resource "archive_file" "zip1" {
  type        = "zip"
  output_path = "bot.zip"
  source_dir  = "bot"
}

resource "archive_file" "zip2" {
  type        = "zip"
  output_path = "crop-face.zip"
  source_dir  = "crop_face"
}

resource "archive_file" "zip3" {
  type        = "zip"
  output_path = "detect-face.zip"
  source_dir  = "detect_face"
}