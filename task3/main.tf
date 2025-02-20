# Настройки Terraform
terraform {
  required_providers {
    yandex = {
      source  = "yandex-cloud/yandex"
      version = "~> 0.135.0"
    }
  }
  required_version = ">= 0.13"
}

variable "zone" {
  type        = string
  description = "Yandex.Cloud Zone"
  default     = "ru-central1-d" # рекомендуемая зона для новых проектов
}

variable "cloud-id" {
  type        = string
  description = "Yandex.Cloud Cloud ID"
}

variable "folder-id" {
  type        = string
  description = "Yandex.Cloud Folder ID"
}

# Настроки провайдера Yandex Cloud
provider "yandex" {
  service_account_key_file = pathexpand("C:/Users/tatya/.yc-keys/key.json")
  cloud_id                 = var.cloud-id
  folder_id                = var.folder-id
  zone                     = var.zone
}

resource "yandex_vpc_network" "network" {
  name = "vvot18-nextcloud-network"
}

resource "yandex_vpc_subnet" "subnet" {
  name           = "vvot18-nextcloud-subnet"
  zone           = var.zone
  v4_cidr_blocks = ["192.168.10.0/24"]
  network_id     = yandex_vpc_network.network.id
}

# Получение  последеней версии публичного образа с Ubuntu 24.04
data "yandex_compute_image" "ubuntu" {
  family = "ubuntu-2404-lts-oslogin"
}

resource "yandex_compute_disk" "boot-disk" {
  name     = "vvot18-nextcloud-boot-disk"
  type     = "network-ssd"
  image_id = data.yandex_compute_image.ubuntu.id
  size     = 20 # Размер диска 10 Гб
}

resource "yandex_compute_instance" "server" {
  name        = "vvot18-nextcloud-server"
  platform_id = "standard-v3"
  hostname    = "nextcloud"

  resources {
    core_fraction = 20
    cores         = 2
    memory        = 4
  }

  boot_disk {
    disk_id = yandex_compute_disk.boot-disk.id
  }

  network_interface {
    subnet_id = yandex_vpc_subnet.subnet.id
    nat       = true
  }

  metadata = {
    ssh-keys = "ubuntu:${file("~/.ssh/id_rsa.pub")}"
  }
}

output "vvot18-nextcloud-server-ip" {
  value = yandex_compute_instance.server.network_interface[0].nat_ip_address
}
