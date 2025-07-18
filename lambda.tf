resource "aws_cloudwatch_log_group" "vault" {
  name = "/aws/lambda/${var.resource_name}"

  retention_in_days = 1
}

resource "aws_lambda_function" "this" {
  function_name = var.resource_name
  role          = aws_iam_role.lambda.arn
  handler       = "lambda_function.lambda_handler"

  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  timeout = 300 # 5 minutes
  runtime = "python3.13"

  logging_config {
    application_log_level = "INFO"
    system_log_level      = "INFO"
    log_format            = "JSON"
  }

  environment {
    variables = {
      AWS_MANG_ACC_ROLE        = var.management_account_role
      AWS_MEMBER_ACC_ROLE_NAME = var.member_account_role_name
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda,
    aws_cloudwatch_log_group.vault
  ]
}

resource "aws_lambda_permission" "parameter_store_value_updates" {
  statement_id  = "ParameterStoreValueUpdates"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.parameter_store_value_updates.arn
}

resource "aws_lambda_permission" "parameter_store_tags" {
  statement_id  = "ParameterStoreTags"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.parameter_store_tags.arn
}