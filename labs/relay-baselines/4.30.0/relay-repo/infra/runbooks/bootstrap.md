# Runbook — bootstrap Relay non-production in a clean account

Owner: the platform team, with sam.o. Run once per account, before CI can plan or apply anything.

CI cannot create its own roles: the apply role is denied any change to the CI roles, the OIDC
provider and the permissions boundary, so that it can never widen its own permissions. These
resources are created, and later changed, by the platform team's bootstrap role:

    aws_iam_policy.boundary
    aws_iam_openid_connect_provider.github
    aws_iam_role.ci_plan, aws_iam_role_policy_attachment.ci_plan_readonly, aws_iam_role_policy.ci_plan_state
    aws_iam_role.ci_apply, aws_iam_role_policy.ci_apply
    aws_iam_policy.agent_quarantine, aws_iam_role.ci_killswitch, aws_iam_role_policy.ci_killswitch (4.23.0)

1. **Account and guardrails exist.** The landing zone has created the account in the
   non-production OU, the SCPs in `infra/org/` are attached, the state bucket and the
   `alias/relay-tofu-state` key exist, and the VPN's route into the VPC range is provided by the
   landing zone's transit network.
2. **Plan the bootstrap set only**, with the platform's bootstrap role:
   `tofu plan -var-file=nonprod.tfvars -target=aws_iam_policy.boundary -target=aws_iam_role.ci_apply ...`
   (every address above), then run the policy checks on its JSON.
3. **Review and apply** with a second platform engineer approving.
4. **Hand over.** From now on every other resource is planned on pull requests and applied from
   the protected `nonprod` environment. A pull request that changes the bootstrap set fails at apply
   by design; the platform team applies it the same way as step 2.
