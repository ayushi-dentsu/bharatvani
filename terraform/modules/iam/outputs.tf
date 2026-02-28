output "iam_usernames" {
  description = "List of IAM usernames created for team members"
  value       = [for user in aws_iam_user.team_members : user.name]
}

output "user_credentials" {
  description = "IAM user credentials for team members (SENSITIVE - store securely)"
  sensitive   = true
  value = {
    for idx, user in aws_iam_user.team_members : user.name => {
      email              = var.team_members[idx]
      console_login_url  = "https://${data.aws_caller_identity.current.account_id}.signin.aws.amazon.com/console"
      username           = user.name
      console_password   = aws_iam_user_login_profile.team_members[idx].password
      password_reset_req = true
      access_key_id      = aws_iam_access_key.team_members[idx].id
      secret_access_key  = aws_iam_access_key.team_members[idx].secret
    }
  }
}
