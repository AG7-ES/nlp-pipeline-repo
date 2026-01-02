variable "aws_region" {
  default = "eu-west-3"
}

variable "my_ip" {
  description = "Local IP address for SSH access"
  type        = string
}

variable "dd_api_key" {
  description = "Datadog API Key"
  type        = string
  sensitive   = true
}

variable "postgres_user" {
  description = "Postgres user name"
  type        = string
  sensitive   = true
}

variable "postgres_password" {
  description = "Postgres password"
  type        = string
  sensitive   = true
}

variable "postgres_db" {
  description = "Postgres db name"
  type        = string
  sensitive   = true
}
