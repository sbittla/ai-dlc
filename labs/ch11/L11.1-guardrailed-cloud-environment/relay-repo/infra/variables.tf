variable "region" {
  type        = string
  description = "One of the regions the organization's guardrails allow (infra/org/scp-deny-regions.json)."
}

variable "account_id" {
  type        = string
  description = "The only account this configuration may change; the provider refuses any other."
}

variable "env" {
  type = string
  validation {
    condition     = contains(["nonprod", "prod"], var.env)
    error_message = "env must be nonprod or prod; labs and sandboxes use their own configuration."
  }
}

variable "owner" {
  type        = string
  description = "The accountable owner of everything this configuration creates."
}

variable "cost_center" {
  type = string
}

variable "data_class" {
  type        = string
  description = "Highest data classification stored. Non-production holds synthetic data only."
  validation {
    condition     = contains(["Public", "Internal", "Confidential", "Restricted"], var.data_class)
    error_message = "Use Relay's four-level data classification."
  }
}

variable "azs" {
  type = list(string)
}

variable "vpc_cidr" {
  type = string
}

variable "vpn_cidr" {
  type        = string
  description = "The company VPN's client range: the only source allowed to reach the internal load balancer."
}

variable "image_tag" {
  type = string
}

variable "service_desired_count" {
  type = number
}

variable "worker_desired_count" {
  type = number
}

variable "proxy_desired_count" {
  type = number
}

variable "db_instance_class" {
  type = string
}

variable "db_multi_az" {
  type = bool
}

variable "triage_model_arn" {
  type        = string
  description = "The one foundation model the worker and agent sandboxes may invoke."
}

variable "certificate_arn" {
  type        = string
  description = "Private certificate for the internal load balancer's HTTPS listener."
}

variable "github_repository" {
  type        = string
  description = "owner/name of the repository whose CI may assume the plan and apply roles."
}

variable "budget_limit_usd" {
  type = number
}

variable "account_budget_limit_usd" {
  type = number
}

variable "budget_emails" {
  type = list(string)
}
