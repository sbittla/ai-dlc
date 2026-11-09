# Data (ADR-014): one customer-managed key, a managed PostgreSQL database with a
# standby in the second zone, one secret, and an encrypted bucket for flow logs.

resource "aws_kms_key" "relay" {
  description             = "Relay ${var.env}: database, secrets, logs, images"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  # The default key policy, plus the CloudWatch Logs service, which needs an explicit
  # grant to encrypt log groups with a customer-managed key.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AccountAdministersTheKeyThroughIAM"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${var.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "CloudWatchLogs"
        Effect    = "Allow"
        Principal = { Service = "logs.${var.region}.amazonaws.com" }
        Action    = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"]
        Resource  = "*"
        Condition = { ArnLike = { "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${var.region}:${var.account_id}:log-group:/relay/${var.env}/*" } }
      },
      {
        # VPC flow logs are delivered to the SSE-KMS bucket by the log delivery service.
        Sid       = "VpcFlowLogDelivery"
        Effect    = "Allow"
        Principal = { Service = "delivery.logs.amazonaws.com" }
        Action    = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey"]
        Resource  = "*"
        Condition = { StringEquals = { "aws:SourceAccount" = var.account_id } }
      },
    ]
  })
}

resource "aws_kms_alias" "relay" {
  name          = "alias/${local.name}"
  target_key_id = aws_kms_key.relay.key_id
}

resource "aws_db_subnet_group" "relay" {
  name       = local.name
  subnet_ids = [aws_subnet.data_a.id, aws_subnet.data_b.id]
}

resource "aws_db_parameter_group" "relay" {
  name   = "${local.name}-pg16"
  family = "postgres16"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
  parameter {
    name  = "log_connections"
    value = "1"
  }
}

# Multi-AZ: a synchronous standby in the other zone, promoted automatically if the
# primary or its zone fails. It does not protect against a bad write or a deleted
# table; backups and point-in-time restore do, and the restore is tested (runbook).
# Application roles log in with short-lived IAM tokens; the master password is
# generated and rotated by RDS in Secrets Manager and never appears in state.
resource "aws_db_instance" "relay" {
  identifier                          = local.name
  engine                              = "postgres"
  engine_version                      = "16"
  instance_class                      = var.db_instance_class
  allocated_storage                   = 20
  max_allocated_storage               = 100
  storage_type                        = "gp3"
  storage_encrypted                   = true
  kms_key_id                          = aws_kms_key.relay.arn
  db_name                             = "relay"
  username                            = "relay_admin"
  manage_master_user_password         = true
  master_user_secret_kms_key_id       = aws_kms_key.relay.arn
  iam_database_authentication_enabled = true
  multi_az                            = var.db_multi_az
  publicly_accessible                 = false
  db_subnet_group_name                = aws_db_subnet_group.relay.name
  parameter_group_name                = aws_db_parameter_group.relay.name
  vpc_security_group_ids              = [aws_security_group.db.id]
  port                                = 5432
  backup_retention_period             = 7
  backup_window                       = "03:00-04:00"
  copy_tags_to_snapshot               = true
  deletion_protection                 = true
  skip_final_snapshot                 = false
  final_snapshot_identifier           = "${local.name}-final"
  auto_minor_version_upgrade          = true
}

# The value is written out of band by the platform team, never by this configuration,
# so it is not in state. Deleting the secret leaves a 7-day recovery window.
resource "aws_secretsmanager_secret" "directory" {
  name                    = "relay/${var.env}/directory"
  kms_key_id              = aws_kms_key.relay.arn
  recovery_window_in_days = 7
}

resource "aws_s3_bucket" "flow_logs" {
  bucket        = "${local.name}-flow-logs-${var.account_id}"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "flow_logs" {
  bucket                  = aws_s3_bucket.flow_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "flow_logs" {
  bucket = aws_s3_bucket.flow_logs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.relay.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "flow_logs" {
  bucket = aws_s3_bucket.flow_logs.id
  rule {
    id     = "expire-30-days"
    status = "Enabled"
    filter {}
    expiration {
      days = 30
    }
  }
}
