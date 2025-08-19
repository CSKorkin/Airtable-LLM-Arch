variable "AIRTABLE_API_KEY" {
  description = "API key for Airtable"
  type        = string
  sensitive   = true
}

variable "AIRTABLE_BASE_ID" {
  description = "Airtable base id"
  type        = string
  sensitive   = true
}

variable "AIRTABLE_APPLICANTS_ID" {
  description = "Airtable Applicants table id"
  type        = string
  sensitive   = true
}

variable "AIRTABLE_DETAILS_ID" {
  description = "Airtable Personal Details table id"
  type        = string
  sensitive   = true
}

variable "AIRTABLE_WORK_ID" {
  description = "Airtable Work Experience table id"
  type        = string
  sensitive   = true
}

variable "AIRTABLE_SALARY_ID" {
  description = "Airtable Salary Preferences table id"
  type        = string
  sensitive   = true
}

variable "AIRTABLE_SHORTLIST_ID" {
  description = "Airtable Shortlisted Leads table id"
  type        = string
  sensitive   = true
}

variable "OPENAI_API_KEY" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
}

variable "aws_region" { type = string default = "us-east-1" }
variable "tags" { type = map(string) default = { project = "airtable-svc" } }