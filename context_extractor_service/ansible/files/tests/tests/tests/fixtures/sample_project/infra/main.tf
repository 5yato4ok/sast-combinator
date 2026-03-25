terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

resource "aws_db_instance" "default" {
  identifier = "myapp-db"
  engine     = "postgres"
  password   = var.db_password
  username   = "admin"
}

resource "aws_secretsmanager_secret" "api_key" {
  name = "myapp/api-key"
}
