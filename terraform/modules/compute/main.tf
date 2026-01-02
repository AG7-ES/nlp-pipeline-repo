data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
}

# --- Bastion Host ASG ---
resource "aws_launch_template" "bastion" {
  name_prefix   = "bastion-lt-"
  image_id      = data.aws_ami.ubuntu.id
  instance_type = "t2.micro"
  key_name      = var.key_name

  network_interfaces {
    associate_public_ip_address = true
    security_groups             = [var.bastion_sg_id]
  }

  tag_specifications {
    resource_type = "instance"
    tags = { Name = "bastion-host" }
  }
}

resource "aws_autoscaling_group" "bastion" {
  name                = "bastion-asg"
  desired_capacity    = 1
  max_size            = 2
  min_size            = 1
  vpc_zone_identifier = var.public_subnets # Bastion goes in Public Subnet
  launch_template {
    id      = aws_launch_template.bastion.id
    version = "$Latest"
  }
}

# --- NLP App ASG ---
resource "aws_launch_template" "app" {
  name_prefix   = "nlp-app-lt-"
  image_id      = data.aws_ami.ubuntu.id
  instance_type = "t3.medium"
  key_name      = var.key_name

  block_device_mappings {
    device_name = "/dev/sda1"
    ebs {
      volume_size = 30
      volume_type = "gp3"
    }
  }

  network_interfaces {
    associate_public_ip_address = false # Private Subnet
    security_groups             = [var.app_sg_id]
  }

  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    POSTGRES_USER     = var.postgres_user
    POSTGRES_PASSWORD = var.postgres_password
    POSTGRES_DB       = var.postgres_db
    DD_API_KEY        = var.dd_api_key
  }))

  tag_specifications {
    resource_type = "instance"
    tags = { Name = "nlp-app-instance" }
  }
}

resource "aws_autoscaling_group" "app" {
  name                = "nlp-app-asg"
  desired_capacity    = 1
  max_size            = 2
  min_size            = 1
  health_check_grace_period = 600
  health_check_type         = "ELB"
  vpc_zone_identifier = var.private_subnets # App goes in Private Subnet
  target_group_arns   = [var.target_group_arn]

  launch_template {
    id      = aws_launch_template.app.id
    version = "$Latest"
  }
}
