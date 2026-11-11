# Rules of engagement and ethics agreement for the red-team exchange

Attacking team: `________` Defending team: `________` Signed: `__________` by every member of both teams and
the security reviewer.

- **Target.** Only the defending team's sandboxed deployment, named here: `________`. Nothing else: no shared
  services, no third parties, no model provider, no person.
- **Window.** From `____-__-__T__:__Z` to `____-__-__T__:__Z`. Findings timed outside it are refused (RT002).
- **Data.** Synthetic data only. Load and cost attacks stay within the sandbox's quota.
- **Catalogue.** Attacks are drawn from the course's attack-class catalogue, version `________`. The log names a
  class and a placeholder variant ID; it never contains attack text. Any exploit code stays in the course
  repository, under this agreement, and is not copied, published or used elsewhere.
- **Severity.** The shared scale: critical, high, medium, low, with the definitions in the course handbook.
- **Stop.** Either team, or the security reviewer, can stop the exchange at once. Anything that touches a system
  outside the target is reported to the security reviewer within one hour.

These techniques are taught for defence, on systems the learners own. Using them anywhere else breaks this
agreement and the learner agreement.
