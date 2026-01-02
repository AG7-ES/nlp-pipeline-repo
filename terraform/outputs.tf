output "alb_dns_name" {
  value = module.lb.alb_dns_name
}

output "private_key_pem" {
  value     = module.security.private_key_pem
  sensitive = true
}

output "bastion_asg_name" {
  value = module.compute.bastion_asg_name
}
