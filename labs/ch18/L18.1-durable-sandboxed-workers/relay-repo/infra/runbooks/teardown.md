# Runbook — tear down Relay non-production

Owner: sam.o. Run by a person from the protected `nonprod` CI environment; agents never run it.
Lab 11.1's `teardown` command checks steps 2, 3 and 5 on the plan and inventory files.

1. **Announce and freeze.** Post the teardown time in the team channel. No applies until step 6.
2. **Prepare in a reviewed change.** Set `deletion_protection = false` on `aws_db_instance.relay`
   and apply that one change. Keep `skip_final_snapshot = false`: the destroy then takes a final
   snapshot named `relay-nonprod-final`.
3. **Plan the destroy and read it.** `tofu plan -destroy -var-file=nonprod.tfvars -out=destroy.tfplan`,
   then `tofu show -json destroy.tfplan > destroy.plan.json`. Every resource must carry
   `env=nonprod` and `app=relay`; the plan must delete nothing else (no shared resources) and
   must delete everything in state.
4. **Destroy.** `tofu apply destroy.tfplan`. Expect the secret to enter its 7-day recovery
   window and the KMS key its 30-day deletion window; both are normal.
5. **Prove nothing is left.** List tagged resources (`aws resourcegroupstaggingapi get-resources
   --tag-filters Key=env,Values=nonprod`). Only the final snapshot may remain, tagged with an
   `expires` date. Untagged resources do not appear in this list: also check Cost Explorer for
   spend with no `env` tag over the following two days.
6. **Record it.** Fill in the teardown record (Lab 11.1, `templates/teardown-record.md`): times,
   the inventory, what was retained and until when, and who approved.
