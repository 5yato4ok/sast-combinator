variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"
}

variable "api_secret" {
  description = "API secret key"
  type        = string
  sensitive   = true
}
