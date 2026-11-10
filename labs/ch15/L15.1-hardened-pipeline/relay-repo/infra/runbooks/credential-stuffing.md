# Runbook — credential stuffing on sign-in

Owner: aisha.r. Alerts: SD-001 (failure surge), SD-002 (many credentials from one network), SD-003 (a success
from a network with many failures). A security incident: P1, the security lead within one hour.

1. Declare a security P1. Do not roll back or scale anything first: an attack is not fixed by a deploy.
2. Contain, through the remediation gate (security on-call approves): tighten the sign-in rate limit per
   network for the networks in SD-002's evidence; require a second factor or a challenge for sign-ins from
   them.
3. For every account in SD-003's evidence, end its sessions and force a password reset. A reset revokes the
   account's personal API tokens; service tokens survive it and are checked separately.
4. Preserve evidence: the security events (network prefixes and keyed fingerprints, never passwords), the
   trail of any agent touched, and the sign-in service's logs for the window.
5. The data protection officer decides, with the security lead, whether customers or authorities must be told.
6. Afterwards: add the attack's shape to the service-detection seeded cases.
