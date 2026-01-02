output "alb_sg_id" { value = aws_security_group.alb.id }
output "bastion_sg_id" { value = aws_security_group.bastion.id }
output "app_sg_id" { value = aws_security_group.app.id }
output "key_name" { value = aws_key_pair.generated_key.key_name }
output "private_key_pem" { value = tls_private_key.pk.private_key_pem }
output "self_signed_cert_arn" { value = aws_acm_certificate.cert.arn }
