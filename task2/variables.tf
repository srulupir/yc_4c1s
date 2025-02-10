variable "telegram_bot_token" {
  type = string
}

variable "folder_id" {
  type = string
}

variable "cloud_id" {
  type = string
}

variable "zone" {
  type = string
}


variable "webhook_url" {
  type = string
}

variable "images_bucket_name" {
  type = string
}

variable "processed_faces_bucket_name" {
  type = string
}

variable "processing_queue_name" {
  type = string
}

variable "api_gateway_name" {
  type = string
}

variable "api_gateway_original_name" {
  type = string
}

variable "detect_face_func_name" {
  type = string
}

variable "crop_face_func_name" {
  type = string
}

variable "tg_bot_func_name" {
  type = string
}

variable "image_upload_trigger_name" {
  type = string
}

variable "queue_trigger_name" {
  type = string
}

variable "service_account_id" {
  type = string
}

