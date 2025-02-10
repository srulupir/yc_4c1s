terraform {
  required_providers {
    yandex = {
      source = "yandex-cloud/yandex"
    }
  }
  required_version = ">= 0.13"
}

provider "yandex" {
  cloud_id                 = var.cloud_id
  folder_id                = var.folder_id
  service_account_key_file = "C:/Users/tatya/.yc-keys/key.json"
}

resource "yandex_storage_bucket" "tg_bucket" {
  bucket    = var.bucket_name
  folder_id = var.folder_id
}

resource "yandex_storage_object" "yandex_gpt" {
  bucket = yandex_storage_bucket.tg_bucket.id
  key    = "instruction.txt"
  source = "instruction.txt"
}

resource "yandex_function" "bot-func" {
  name               = "bot-func"
  user_hash          = archive_file.zip.output_sha256
  runtime            = "python312"
  entrypoint         = "bot.handler"
  memory             = 128
  execution_timeout  = 20
  service_account_id = var.service_account_id

  environment = {
    TG_BOT_KEY            = var.tg_bot_key,
    YC_BUCKET_NAME        = var.bucket_name
    YC_FOLDER_ID          = var.folder_id
    AWS_ACCESS_KEY_ID     = var.aws_access_key_id,
    AWS_SECRET_ACCESS_KEY = var.aws_secret_access_key,
    YANDEX_API_KEY        = var.yandex_api_key
  }

  mounts {
    name = var.bucket_name
    mode = "ro"
    object_storage {
      bucket = yandex_storage_bucket.tg_bucket.bucket
    }
  }

  content {
    zip_filename = archive_file.zip.output_path
  }
}

resource "archive_file" "zip" {
  type        = "zip"
  output_path = "src.zip"
  source_dir  = "src"
}

output "func_url" {
  value = "https://functions.yandexcloud.net/${yandex_function.bot-func.id}"
}

resource "yandex_function_iam_binding" "function-iam" {
  function_id = yandex_function.bot-func.id
  role        = "functions.functionInvoker"

  members = ["system:allUsers",]
}


resource "null_resource" "triggers" {
  triggers = {
    api_key = var.tg_bot_key
  }

  provisioner "local-exec" {
    command = "curl --insecure -X POST https://api.telegram.org/bot${var.tg_bot_key}/setWebhook?url=https://functions.yandexcloud.net/${yandex_function.bot-func.id}"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "curl --insecure -X POST https://api.telegram.org/bot${self.triggers.api_key}/deleteWebhook"
  }
}
