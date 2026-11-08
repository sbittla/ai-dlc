# Webhook Delivery and Retries

Workflow webhooks are delivered with an HMAC-SHA256 signature in the X-Relay-Signature header. Receivers must verify the signature using the webhook secret shown once at creation time.

Failed deliveries are retried 8 times with exponential backoff, the last attempt about 6 hours after the first. After the final failure the webhook is marked "degraded" and the workspace owner receives an email.

Webhook payloads never include attachment contents, only attachment IDs. Payloads larger than 256 KB are truncated and flagged with "truncated": true.
