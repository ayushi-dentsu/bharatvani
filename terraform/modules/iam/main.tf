# Data source for AWS account ID
data "aws_caller_identity" "current" {}

# Create IAM users for team members
resource "aws_iam_user" "team_members" {
  count = length(var.team_members)
  name  = "bharatvani-${split("@", var.team_members[count.index])[0]}"

  tags = {
    Name        = "bharatvani-${split("@", var.team_members[count.index])[0]}"
    Email       = var.team_members[count.index]
    Project     = var.project_name
    Environment = var.environment
  }
}

# Create login profiles for console access
resource "aws_iam_user_login_profile" "team_members" {
  count = length(var.team_members)
  user  = aws_iam_user.team_members[count.index].name

  # Generate a random password that will be accessible in outputs
  password_length         = 20
  password_reset_required = true

  lifecycle {
    ignore_changes = [
      password_length,
      password_reset_required,
    ]
  }
}

# Attach AdministratorAccess policy to each user
resource "aws_iam_user_policy_attachment" "admin_access" {
  count      = length(var.team_members)
  user       = aws_iam_user.team_members[count.index].name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

# Generate access keys for programmatic access
resource "aws_iam_access_key" "team_members" {
  count = length(var.team_members)
  user  = aws_iam_user.team_members[count.index].name
}
