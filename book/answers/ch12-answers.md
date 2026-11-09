# Chapter 12 — Answers and Marking Notes

Numbers in these answers were checked by running code from `labs/ch12/L12.1-agentic-red-team/solution/redteam/` and `labs/ch12/L12.2-malicious-mcp-server/solution/mcpguard/`, including a modified copy of the control catalogue for Exercise 6. They are locked by Lab 12.1's `tests/test_answers.py` and the two labs' golden tests. The attack classes and scenarios are generated, and every payload is an inert placeholder. No answer here quotes an attack success rate for Relay, because none has been measured against the deployed model.

## Recall

**1. The five boundaries.**

| Boundary | Who can write what crosses it in the summary pilot |
| --- | --- |
| Prompt | Relay's engineers, through reviewed code |
| Context | Anyone who can file a ticket, including a trial account; whoever wrote the tickets the search returned |
| Tools | The model, steered by its context; the search ran with the worker's authority |
| Memory | The pilot kept none; in 4.26.0 the model proposes and a person accepts |
| Output | The model; then the engineer's browser acted on it by fetching the image |

Full marks need all five, and the point that the output boundary includes the reader's browser, which no workload egress rule covers.

**2. Spotlighting as mitigating.** Marking changes what the model sees, not what the system can do. Whether it stops an attack depends on whether the model obeys, which only a measurement against the model can show. A probe can show the mechanism works (the envelope is applied, hidden characters removed, imitation markers neutralized), but not that the effect is impossible. The output constraint and renderer hold whether or not the model obeyed, so they can be verified as blocking. Full marks contrast "lowers obedience" with "makes the effect impossible".

**3. Rug pull, shadowing and name collision.**

- A rug pull is one server changing after its review while keeping its approved name and launch command. The pin check catches it (MCP010, or MCP011 for a new tool), and in Lab 12.2 it is the only check that catches S04, S13, S14 and S15.
- Tool shadowing, in Invariant Labs' usage, is a description that steers how the agent uses another server's tool. No host check catches it once a reviewer has approved it: the pin freezes the approved description (S12). Only reading descriptions at review catches it.
- A tool name collision is two servers offering one tool name. The name-collision check catches it (MCP020), and it is the only check that catches S11, where both servers passed their own reviews.

Full marks need all three and the point that pins catch change, not a poisoned description approved at review.

**4. Why egress did not help.** The data left through the support engineer's browser, which requested the image when the console rendered the summary. The egress proxy governs Relay's workloads and agent sandboxes, not a person's browser. The controls on that path are in the output: `parse_summary` drops the summary, and `render_text` never emits an image. A Content-Security-Policy in the client is a further layer.

## Apply

**5. The 4.25.0 failures.** The failed cells are C10 and C11, both tested with `egress_domain_only`, the 4.25.0 allowlist. That proxy checks only the CONNECT host's name and splices every tunnel, so it cannot see paths, server names in the handshake or Host headers.

- C10's variants all name `api.github.com`, or a mismatched server name on an allowed CONNECT, so all 8 get through.
- C11's set has one variant whose host is not on the allowlist at all, and the name check refuses it, so 1 of 8 is stopped.

In 4.26.0, ADR-035 decrypts the content hosts and allows only Relay's repository. Each splice or bump rule needs both the CONNECT host and the server name on its list, everything else is terminated, and decrypted requests have their Host header checked, so both cells are verified. Full marks name both cells and the names-not-paths reason.

**6. C05's coverage.** Coverage is the largest set of verified controls whose failure domains are disjoint.

- The tool allowlist depends on the boundary, the session and the identity module. The approval gate depends on the boundary and the approval module. They share the boundary, so together they count once.
- The platform permissions depend on the GitHub App and branch protection, outside Relay's code, so they are the second.
- A fault in the boundary drops C05 to 1: the domains report shows `relay.agents.boundary` taking seven classes below the policy.

If the approval gate did not run inside the boundary, it would be independent of the allowlist. C05's coverage would be 3, and a boundary fault would leave it at 2, still meeting the policy. Strong answers add two points. Failure domains are declared by people, so an undeclared shared dependency stays invisible. And an approval that is not enforced inside the boundary needs another way to stop the call from running without it.

**7. A webhook adapter.** Marking notes; no single right answer.

- **Classes it adds:** data out through a webhook to a URL an attacker configured (exfiltration); a request to an internal address through a customer-set URL (server-side request forgery, unauthorised action); event content carrying task text (exfiltration, ESC-N07).
- **Controls to claim:** URLs validated at save time and again at send time (https only, no internal or link-local addresses after resolution, no redirects); the body built only from the engine's fields, which hold no task content; signing with the webhook secret; delivery through the egress proxy with its own allowlist policy for customer endpoints; one adapter module admitted by its own ADR (FF004).
- **Probes:** a save with an internal address is refused; a send that resolves to an internal address is refused; a body built from a task with a sensitive title holds no part of it; a legitimate customer endpoint receives a correctly signed event.

Full marks need at least two classes, two controls each in different modules for the exfiltration classes, and a legitimate case for every probe.

## Design

**8. Links to help articles.** Marking notes. The aim is that C01 to C04 keep coverage 2.

- **`render_text`:** add a second allowlist of exact help-centre URL prefixes on Relay's own documentation host, still https, with no query string. Never allow the whole host, if anyone outside Relay can publish under it.
- **`parse_summary`:** today it is an allowlist with no slash, so it refuses every address. Keep it, and let the model return article IDs that Relay turns into links. Adding a slash to the allowlist would reopen every address shape the renderer alone would then have to stop, leaving the four classes with one control.
- **Catalogue:** a class for a link to an attacker's page that looks like a help article (phishing through the summary), and one for data carried in a help-article URL's path.
- **Probes:** legitimate cases of a real article link rendering as clickable, end to end, and attack variants of a lookalike host, a path carrying data, and a query string. The two controls must still share no code.

Strong answers choose IDs over addresses and explain why.

**9. The live red-team exercise.** Marking notes; a strong design includes:

- **Set:** a versioned attack set (dev and held-out, split by family) with real attack cases. Keep it in a restricted repository, not a book.
- **Configurations:** the deployed model and prompt, with each defence layer on and off.
- **Goals:** judged by effects observed in a sandbox with canary data and sinks under reserved domains, never by the model's text.
- **Statistics:**
  - repeated runs per case, because models are nondeterministic;
  - the attack success rate per configuration, computed per case first (the share of a case's runs that succeed, or whether any run succeeds), with an interval that resamples cases, such as a bootstrap over cases or families. Repeated runs of one case are correlated, so a Wilson interval over all runs would be too narrow;
  - paired tests between configurations at the case level, such as exact McNemar on whether each case succeeded;
  - a sample size chosen in advance for the difference worth detecting.
- **Results:** reported beside the coverage gate's matrix, owned by aisha.r, and re-run on every model change.

It can show how often the model is steered into trying an effect. That is the input to an autonomy decision above T2, and it can find classes the catalogue missed. The coverage gate cannot show either. Full marks need effect-based judging, intervals and paired tests, and the point that the measurement complements rather than replaces the gate.
