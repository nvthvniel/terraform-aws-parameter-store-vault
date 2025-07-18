# terraform-aws-parameter-store-vault
Terraform module for building a distributed Parameter Store secrets vault

- [Blog Post](https://hello.nathanielstevens.app/posts/parameter_store_vault)

## Deployment

### Vault Account

- This Terraform Module is designed to be hosted in a dedicated 'vault' AWS account.
- When a Parameter is created or modified, prefixed with `/vault/` path, an event bridge rule will trigger a Lambda function.
- The Lambda function will clone or sync the secret with target sharing accounts defined using tags.

```terraform
provider "aws" {
  region = "eu-west-2"
}

module "parameter_store_vault" {
  source = "git@github.com:nvthvniel/terraform-aws-parameter-store-vault.git//terraform?ref=vx.x.x"

  # Common name for all resources created
  resource_name = "secrets-vault"

  # ARN of IAM Role within AWS Management Account
  # Used to enumerate Organisational structure
  management_account_role = "arn:aws:iam::112233445566:role/secrets-vault"

  # Name of IAM Roles in AWS Organisation member accounts that will be shared to
  member_account_role_name = "secrets-vault"
}
```

### AWS Organisation Management Account

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::VAULT-ACCOUNT-ID:role/secrets-vault-lambda"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
```

```json
{
"Statement": [
        {
            "Sid": "Organisations"
            "Action": [
                "organizations:ListAccountsForParent",
                "organizations:ListAccounts"
            ],
            "Effect": "Allow",
            "Resource": "*",
        },
        {
            "Sid": "ParameterStore"
            "Action": [
                "ssm:PutParameter",
                "ssm:GetParameters",
                "ssm:DeleteParameter",
                "ssm:AddTagsToResource"
            ],
            "Effect": "Allow",
            "Resource": "arn:aws:ssm:*:*:parameter/vault/*",
        }
    ],
    "Version": "2012-10-17"
}
```

### AWS Organisation Member Account

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "Lambda"
            "Effect": "Allow",
            "Principal": {
                "Service": "lambda.amazonaws.com"
            },
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {
                    "aws:SourceArn": "arn:aws:lambda:AWS-REGION:VAULT-ACCOUNT-ID:function:secrets-vault"
                }
            }
        }
    ]
}
```

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "CloudWatch",
            "Action": [
                "logs:PutLogEvents",
                "logs:CreateLogStream",
                "logs:CreateLogGroup"
            ],
            "Effect": "Allow",
            "Resource": "arn:aws:logs:AWS-REGION:VAULT-ACCOUNT-ID:log-group:/aws/lambda/secrets-vault:*",
        },
        {
            "Sid": "STS",
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Resource": "arn:aws:iam::*:role/secrets-vault",
        },
        {
            "Sid": "ParameterStoreGlobal",
            "Action": "ssm:DescribeParameters",
            "Effect": "Allow",
            "Resource": "arn:aws:ssm:AWS-REGION:VAULT-ACCOUNT-ID:*",
        },
        {
            "Sid": "ParameterStoreLocal",
            "Action": [
                "ssm:ListTagsForResource",
                "ssm:GetParameter*"
            ],
            "Effect": "Allow",
            "Resource": "arn:aws:ssm:AWS-REGION:VAULT-ACCOUNT-ID:parameter/vault/*",
        }
    ]
}
```

## Usage

### Tags
- `112233445566:true` share with specific AWS Account 
- `ou-xxx:true` share with all AWS Accounts contained in an AWS Organisational Unit
- `r-xxx:true` share will all AWS Accounts in an AWS Organisation
