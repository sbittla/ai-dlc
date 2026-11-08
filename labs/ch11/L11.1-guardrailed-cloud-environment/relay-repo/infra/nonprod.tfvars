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

image_tag             = "4.21.0"
service_desired_count = 2
worker_desired_count  = 1
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
