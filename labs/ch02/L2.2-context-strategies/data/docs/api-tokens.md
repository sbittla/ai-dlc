# API Tokens

Personal API tokens inherit the permissions of the user who created them. Changing or resetting that user's password revokes all of their personal tokens immediately.

For integrations, Relay recommends service tokens, which belong to the workspace rather than a person and survive password changes. Service tokens can be scoped to read-only or read-write, per project.

Tokens are shown only once at creation. Relay stores a hash, not the token, so lost tokens cannot be recovered and must be replaced.
