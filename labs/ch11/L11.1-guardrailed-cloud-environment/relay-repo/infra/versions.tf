# Relay's non-production environment on AWS (Relay 4.21.0; ADR-012 to ADR-015).
#
#   tofu init
#   tofu plan -var-file=nonprod.tfvars -out=nonprod.tfplan
#   tofu show -json nonprod.tfplan > nonprod.plan.json     # what the policy checks read
#
# CI runs plan with the ci_plan role (read-only, OIDC) on every pull request that
# touches infra/, then the policy checks and the cost estimate. Apply and destroy
# run only from the protected "nonprod" environment with the ci_apply role, after
# a person has reviewed the plan. Agents never run apply or destroy (AGENTS.md).

terraform {
  required_version = ">= 1.10.0" # S3 use_lockfile needs 1.10

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }

  # Remote state in the platform team's state bucket (created by the landing zone,
  # not by this configuration). State can hold sensitive values, so the bucket is
  # private, versioned and KMS-encrypted, and only the two CI roles can read it.
  backend "s3" {
    bucket       = "relay-tofu-state-111122223333"
    key          = "nonprod/relay.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }

  # OpenTofu only: client-side encryption of state and plan files, on top of the
  # bucket's own encryption. Terraform does not support this block.
  encryption {
    key_provider "aws_kms" "state" {
      kms_key_id = "alias/relay-tofu-state"
      region     = "us-east-1"
      key_spec   = "AES_256"
    }
    method "aes_gcm" "state" {
      keys = key_provider.aws_kms.state
    }
    state {
      method = method.aes_gcm.state
    }
    plan {
      method = method.aes_gcm.state
    }
  }
}
