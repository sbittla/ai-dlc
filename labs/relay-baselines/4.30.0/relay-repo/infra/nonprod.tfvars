# Relay non-production. Synthetic data only (Internal); no customer data.
region      = "us-east-1"
account_id  = "111122223333"
env         = "nonprod"
owner       = "sam.o"
cost_center = "relay-eng"
data_class  = "Internal"

azs      = ["us-east-1a", "us-east-1b"]
vpc_cidr = "10.40.0.0/16"
vpn_cidr = "10.255.0.0/16"

# Digests of the images the 4.25.0 release workflow signed (ADR-028). The values in this
# snapshot are lab stand-ins: a real deployment takes them from the release's signed SBOM.
image_digest       = "sha256:8d0eeba9d26884f38d5e97f75f1314f80ab8e7b6b7999544d4b484ecbe300b0c"
proxy_image_digest = "sha256:65a344b52988571e5cf8315e478627f543c19520fd1ea0624e61437000b55d94"
link_base          = "https://relay.example/ws-nonprod"

# Zero until the PostgreSQL store adapter exists (ADR-014, ADR-031): the service refuses to start
# without it, and the worker would run alone on a private file. The wiring is checked by tests.
service_desired_count = 0
worker_desired_count  = 0
proxy_desired_count   = 1

db_instance_class = "db.t4g.small"
db_multi_az       = true

# Placeholder model ARN: replace with the model the triage evaluation approved (Chapter 7).
triage_model_arn = "arn:aws:bedrock:us-east-1::foundation-model/example.triage-model-v1:0"
certificate_arn  = "arn:aws:acm:us-east-1:111122223333:certificate/00000000-0000-0000-0000-000000000000"

github_repository = "relay-example/relay"

budget_limit_usd         = 300
account_budget_limit_usd = 400
budget_emails            = ["relay-platform-alerts@example.com"]
