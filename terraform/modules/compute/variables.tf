variable "vpc_id" {}
variable "private_subnets" { type = list(string) }
variable "public_subnets" { type = list(string) }
variable "app_sg_id" {}
variable "bastion_sg_id" {}
variable "key_name" {}
variable "target_group_arn" {}
variable "dd_api_key" {}
variable "postgres_user" {}
variable "postgres_password" {}
variable "postgres_db" {}
