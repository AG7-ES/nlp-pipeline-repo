module "networking" {
  source = "./modules/networking"
  vpc_cidr = "10.0.0.0/16"
}

module "security" {
  source = "./modules/security"
  vpc_id = module.networking.vpc_id
  my_ip  = var.my_ip
}

module "lb" {
  source            = "./modules/lb"
  vpc_id            = module.networking.vpc_id
  public_subnets    = module.networking.public_subnet_ids
  alb_sg_id         = module.security.alb_sg_id
  certificate_arn   = module.security.self_signed_cert_arn # Using self-signed for demo
}

module "compute" {
  source             = "./modules/compute"
  vpc_id             = module.networking.vpc_id
  private_subnets    = module.networking.private_subnet_ids
  public_subnets     = module.networking.public_subnet_ids
  app_sg_id          = module.security.app_sg_id
  bastion_sg_id      = module.security.bastion_sg_id
  key_name           = module.security.key_name
  target_group_arn   = module.lb.target_group_arn
  
  # Environment Variables
  dd_api_key         = var.dd_api_key
  postgres_user      = var.postgres_user
  postgres_password  = var.postgres_password
  postgres_db        = var.postgres_db
}
