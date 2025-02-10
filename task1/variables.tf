
variable "service_account_id" {
  type        = string
}

variable "tg_bot_key" {
  type        = string
}

variable "cloud_id" {
  type        = string
}

variable "folder_id" {
  type        = string
}

variable "bucket_name" {
  type        = string
}

variable "aws_access_key_id" {
  type        = string
  sensitive   = true
}

variable "aws_secret_access_key" {
  type        = string
  sensitive   = true
}

variable "yandex_api_key" {
  type        = string
  sensitive   = true
}