# Single Sign-On Setup

Relay supports SAML 2.0 and OpenID Connect. SSO is available on the Business plan only.

SAML signing certificates must be rotated before they expire; Relay warns workspace owners 30 days and 7 days before expiry. If a certificate expires, all SSO logins fail until a new certificate is uploaded.

SSO sessions last 12 hours by default. Admins can shorten the session length to as little as 15 minutes in Security settings, which is a common cause of "logged out every 15 minutes" reports.
