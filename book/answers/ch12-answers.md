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

**3. Rug pull and shadowing.** A rug pull is one server changing after its review while keeping its approved name and launch command; the pin check catches it (MCP010), and in Lab 12.2 it is the only check that catches S04. Tool shadowing is a second server offering a tool name another server offers; the shadowing check catches it (MCP020), and it is the only check that catches S11, where both servers passed their own reviews. Full marks need both definitions and both checks.

**4. Why egress did not help.** The data left through the support engineer's browser, which requested the image when the console rendered the summary. The egress proxy governs Relay's workloads and agent sandboxes, not a person's browser. The controls on that path are in the output: `parse_summary` drops the summary, and `render_text` never emits an image. A Content-Security-Policy in the client is a further layer.

## Apply

**5. The 4.25.0 failure.** The failed cell is C10 with `egress_domain_only`. C10's target is an attacker's repository on `api.github.com`. The 4.25.0 proxy allows that host by name, and it cannot see paths, so the request is allowed and the probe fails. C11's target is a host not on the allowlist at all, so the domain-only check refuses it and the cell is verified. In 4.26.0, ADR-035 decrypts the content hosts and allows only Relay's repository, so C10 is verified. Full marks name C10, the host, and the names-not-paths reason.

**6. Memory trust and memory review.** Coverage counts distinct modules among verified controls. Both controls are in `relay.agents.memory`, so for C12 and C13 they count as one module; recall taint, in `relay.agents.boundary`, is the second. Removing either memory control leaves the other in the same module, so coverage stays 2 and nothing falls short. Removing recall taint drops C12 and C13 to 1 of 2.

If memory review moved into its own module, C12's coverage would be 3. Then recall taint would no longer be load-bearing for the gate: removing it would leave 2. Strong answers add that a module boundary is a proxy for independence. A path that bypasses the memory store's API could still defeat both, and a person accepting a plausible fact is a third failure mode that no module split addresses.

**7. A webhook adapter.** Marking notes; no single right answer.

- **Classes it adds:** data out through a webhook to a URL an attacker configured (exfiltration); a request to an internal address through a customer-set URL (server-side request forgery, unauthorised action); event content carrying task text (exfiltration, ESC-N07).
- **Controls to claim:** URLs validated at save time and again at send time (https only, no internal or link-local addresses after resolution, no redirects); the body built only from the engine's fields, which hold no task content; signing with the webhook secret; delivery through the egress proxy with its own allowlist policy for customer endpoints; one adapter module admitted by its own ADR (FF004).
- **Probes:** a save with an internal address is refused; a send that resolves to an internal address is refused; a body built from a task with a sensitive title holds no part of it; a legitimate customer endpoint receives a correctly signed event.

Full marks need at least two classes, two controls each in different modules for the exfiltration classes, and a legitimate case for every probe.

## Design

**8. Links to help articles.** Marking notes.

- **`render_text`:** add a second allowlist of exact help-centre URL prefixes on Relay's own documentation host, still https, with no query string. Never allow the whole host, if anyone outside Relay can publish under it.
- **`parse_summary`:** today it refuses every address. Either allow only addresses that match the same reviewed prefixes, or keep refusing addresses and let the model return article IDs that Relay turns into links. The second is stronger, because the model then never writes an address.
- **Catalogue:** a class for a link to an attacker's page that looks like a help article (phishing through the summary), and one for data carried in a help-article URL's path.
- **Probes:** legitimate cases of a real article link rendering as clickable, and attack cases of a lookalike host, a path carrying data, and a query string. The gate must still show two verified modules for each exfiltration class.

Strong answers choose IDs over addresses and explain why.

**9. The live red-team exercise.** Marking notes; a strong design includes:

- **Set:** a versioned attack set (dev and held-out, split by family) with real attack cases. Keep it in a restricted repository, not a book.
- **Configurations:** the deployed model and prompt, with each defence layer on and off.
- **Goals:** judged by effects observed in a sandbox with canary data and sinks under reserved domains, never by the model's text.
- **Statistics:**
  - repeated runs per case, because models are nondeterministic;
  - the attack success rate per configuration with a Wilson interval;
  - paired tests (exact McNemar) between configurations;
  - a sample size chosen in advance for the difference worth detecting.
- **Results:** reported beside the coverage gate's matrix, owned by aisha.r, and re-run on every model change.

It can show how often the model is steered into trying an effect. That is the input to an autonomy decision above T2, and it can find classes the catalogue missed. The coverage gate cannot show either. Full marks need effect-based judging, intervals and paired tests, and the point that the measurement complements rather than replaces the gate.
