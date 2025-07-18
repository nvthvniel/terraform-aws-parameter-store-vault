resource "aws_iam_role" "lambda" {
  name = "${var.resource_name}-lambda"

  assume_role_policy = data.aws_iam_policy_document.lambda_trust_relationship.json
}

resource "aws_iam_policy" "lambda" {
  name   = "${var.resource_name}-lambda"
  path   = "/"
  policy = data.aws_iam_policy_document.lambda_permission_policy.json
}

resource "aws_iam_role_policy_attachment" "lambda" {
  role       = aws_iam_role.lambda.name
  policy_arn = aws_iam_policy.lambda.arn
}