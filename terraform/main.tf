# --- SSM parameters (store your keys here) ---
resource "aws_ssm_parameter" "third_party_api_key" {
  name  = "/airtable-svc/THIRD_PARTY_API_KEY"
  type  = "SecureString"
  value = "REPLACE_ME" # or put it manually in console; never commit secrets
}

# --- IAM role for Lambdas ---
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_role" {
  name               = "airtable-svc-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Allow reading SSM parameters
resource "aws_iam_policy" "ssm_read" {
  name   = "airtable-svc-ssm-read"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action   = ["ssm:GetParameter","ssm:GetParameters","ssm:GetParametersByPath"],
      Effect   = "Allow",
      Resource = "arn:aws:ssm:*:*:parameter/airtable-svc/*"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm_read_attach" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.ssm_read.arn
}

# --- Lambda: create_json ---
resource "aws_lambda_function" "create_json_fn" {
  function_name = "create-json-fn"
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  architectures = ["x86_64"]

  # note: terraform/ is your cwd; zips live one level up
  filename         = "../dist/create_lambda.zip"
  source_code_hash = filebase64sha256("../dist/create_lambda.zip")

  environment {
    variables = {
      AIRTABLE_API_KEY        = var.AIRTABLE_API_KEY
      AIRTABLE_BASE_ID        = var.AIRTABLE_BASE_ID
      AIRTABLE_APPLICANTS_ID  = var.AIRTABLE_APPLICANTS_ID
      AIRTABLE_DETAILS_ID     = var.AIRTABLE_DETAILS_ID
      AIRTABLE_WORK_ID        = var.AIRTABLE_WORK_ID
      AIRTABLE_SALARY_ID      = var.AIRTABLE_SALARY_ID
      AIRTABLE_SHORTLIST_ID   = var.AIRTABLE_SHORTLIST_ID
      OPENAI_API_KEY          = var.OPENAI_API_KEY
    }
  }

  ephemeral_storage { size = 10240 } # MB (10GB max)
  timeout      = 60
  memory_size  = 512
}

# --- Lambda: decompress_json ---
resource "aws_lambda_function" "decompress_json_fn" {
  function_name = "decompress-json-fn"
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  architectures = ["x86_64"]

  filename         = "../dist/decompress_lambda.zip"
  source_code_hash = filebase64sha256("../dist/decompress_lambda.zip")

  environment {
    variables = {
      AIRTABLE_API_KEY        = var.AIRTABLE_API_KEY
      AIRTABLE_BASE_ID        = var.AIRTABLE_BASE_ID
      AIRTABLE_APPLICANTS_ID  = var.AIRTABLE_APPLICANTS_ID
      AIRTABLE_DETAILS_ID     = var.AIRTABLE_DETAILS_ID
      AIRTABLE_WORK_ID        = var.AIRTABLE_WORK_ID
      AIRTABLE_SALARY_ID      = var.AIRTABLE_SALARY_ID
      AIRTABLE_SHORTLIST_ID   = var.AIRTABLE_SHORTLIST_ID
    }
  }

  ephemeral_storage { size = 10240 }
  timeout      = 120
  memory_size  = 1024
}

# --- HTTP API (API Gateway v2) ---
resource "aws_apigatewayv2_api" "http" {
  name          = "airtable-svc-http-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true
}

# Integrations
resource "aws_apigatewayv2_integration" "create_integ" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.create_json_fn.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "decompress_integ" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.decompress_json_fn.invoke_arn
  payload_format_version = "2.0"
}

# Routes
resource "aws_apigatewayv2_route" "create_route" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "POST /create-json"
  target    = "integrations/${aws_apigatewayv2_integration.create_integ.id}"
}

resource "aws_apigatewayv2_route" "decompress_route" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "POST /decompress-json"
  target    = "integrations/${aws_apigatewayv2_integration.decompress_integ.id}"
}

# Permissions for API Gateway to call Lambda
resource "aws_lambda_permission" "create_allow_invoke" {
  statement_id  = "AllowAPIGInvokeCreate"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.create_json_fn.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}

resource "aws_lambda_permission" "decompress_allow_invoke" {
  statement_id  = "AllowAPIGInvokeDecompress"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.decompress_json_fn.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}

output "base_url" {
  value = aws_apigatewayv2_api.http.api_endpoint
}
