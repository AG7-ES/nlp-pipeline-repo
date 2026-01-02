# --- SSH Key Pair ---
resource "tls_private_key" "pk" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "generated_key" {
  key_name   = "nlp-ssh-key"
  public_key = tls_private_key.pk.public_key_openssh
}

# --- Self-Signed Cert for HTTPS (Development Only) ---
# In production, verify a domain via AWS ACM
resource "tls_self_signed_cert" "example" {
  private_key_pem = tls_private_key.pk.private_key_pem

  subject {
    common_name  = "nlp-app.local"
    organization = "NLP Corp"
  }
  validity_period_hours = 8760
  allowed_uses          = ["key_encipherment", "digital_signature", "server_auth"]
}

resource "aws_acm_certificate" "cert" {
  private_key      = tls_private_key.pk.private_key_pem
  certificate_body = tls_self_signed_cert.example.cert_pem
}

# --- Security Groups ---

# 1. ALB Security Group (Public)
resource "aws_security_group" "alb" {
  name        = "nlp-alb-sg"
  vpc_id      = var.vpc_id
  description = "Allow HTTP/HTTPS from Internet"

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 2. Bastion Security Group (Public)
resource "aws_security_group" "bastion" {
  name        = "nlp-bastion-sg"
  vpc_id      = var.vpc_id
  description = "Allow SSH from Admin IP"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip] # Restricted to your IP
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 3. Application Security Group (Private)
resource "aws_security_group" "app" {
  name        = "nlp-app-sg"
  vpc_id      = var.vpc_id
  description = "Allow traffic from ALB and Bastion"

  # Allow FastAPI (8000) from ALB
  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  # Allow SSH from Bastion
  ingress {
    from_port       = 22
    to_port         = 22
    protocol        = "tcp"
    security_groups = [aws_security_group.bastion.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
