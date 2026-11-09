locals {
  name = "relay-${var.env}"

  # Every taggable resource gets these through default_tags; the policy checks read
  # tags_all in the plan, which includes them.
  tags = {
    app           = "relay"
    env           = var.env
    owner         = var.owner
    "cost-center" = var.cost_center
    "data-class"  = var.data_class
  }
}

provider "aws" {
  region = var.region

  # A plan or apply with credentials for any other account fails before it changes
  # anything (compare Chapter 3's incident, where the wrong credentials were in reach).
  allowed_account_ids = [var.account_id]

  default_tags {
    tags = local.tags
  }
}
