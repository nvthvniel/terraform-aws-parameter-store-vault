variable "resource_name" {
  description = "Common name for resources"
  type        = string
  default     = "secrets-vault"
}

variable "management_account_role" {
  description = "ARN of IAM role in AWS Organisations management account. Used for discovering organisation structure for sharing parameters"
  type        = string
}

variable "member_account_role_name" {
  description = "Name of IAM roles in member accounts that should be assumed to manage parameters"
  type        = string
  default     = "secrets-vault"
}