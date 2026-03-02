variable "team_members" {
  description = "List of team member email addresses for IAM user creation"
  type        = list(string)
}

variable "environment" {
  description = "Environment name (dev/demo/prod)"
  type        = string
}

variable "project_name" {
  description = "Project name for resource tagging"
  type        = string
}
