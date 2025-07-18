resource "aws_cloudwatch_event_rule" "parameter_store_value_updates" {
  name        = "${var.resource_name}-value-updates"
  description = "Updates to Parameter Store values"

  event_pattern = jsonencode({
    source      = ["aws.ssm"],
    detail-type = ["Parameter Store Change"],
    operation : ["Update"],
    detail = {
      name = [
        {
          prefix = {
            "equals-ignore-case" : "/vault/"
          }
        }
      ]
    }
  })
}

resource "aws_cloudwatch_event_target" "parameter_store_value_updates" {
  arn  = aws_lambda_function.this.arn
  rule = aws_cloudwatch_event_rule.parameter_store_value_updates.id

  retry_policy {
    maximum_retry_attempts       = 0
    maximum_event_age_in_seconds = 86400 # 1 day
  }
}



resource "aws_cloudwatch_event_rule" "parameter_store_tags" {
  name        = "${var.resource_name}-tags"
  description = "tagging operations on parameter store entries"

  event_pattern = jsonencode({
    source      = ["aws.tag"],
    detail-type = ["Tag Change on Resource"],
    resources = [
      {
        "prefix" : "arn:aws:ssm:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:parameter/vault/"
      }
    ]

  })
}

resource "aws_cloudwatch_event_target" "parameter_store_tags" {
  arn  = aws_lambda_function.this.arn
  rule = aws_cloudwatch_event_rule.parameter_store_tags.id

  retry_policy {
    maximum_retry_attempts       = 0
    maximum_event_age_in_seconds = 86400 # 1 day
  }
}