# API Rate Limits

Relay's public REST API allows 600 requests per minute per workspace token. Burst traffic above the limit receives HTTP 429 with a Retry-After header in seconds.

Bulk endpoints, such as task import, count as 10 requests each. The export endpoint is limited separately to 5 concurrent export jobs per workspace.

Clients should back off exponentially, starting at the Retry-After value. Repeated violations for more than 15 minutes trigger an alert to Relay's platform on-call engineer, who may contact the customer.
