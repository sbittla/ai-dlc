# ADR-032 — Untrusted ticket text: marked on the way in, constrained on the way out, rendered without images

Status: accepted
Date: 2027-02-08
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering), tomas.b (support)
Links: D3, ESC-N01, ESC-N07, CON-4
Related: ADR-007, ADR-017, ADR-023, ADR-034, ADR-035
Revisit when: the triage summary gains a tool, a second consumer renders model-written text, or the
control matrix fails relay-coverage-gate-v1. Review by 2027-08-08 in any case.
Supersedes: none.

## Context

On Tuesday 2 February 2027 a support ticket carried an instruction, hidden in an HTML comment, for the
summary feature that support staff were piloting. The pilot's model searched other customers' tickets and
wrote their contact details into a Markdown image address. The support console rendered the summary, so the
browser of the person who opened the ticket fetched the image from a server outside Relay. Chapter 12
tells the story (a composite).

Three things made it work: the model read ticket text as instructions, its output was free Markdown, and
the client rendered images from any host. Egress rules for Relay's workloads did not apply, because the
request came from a person's browser.

## Options considered

### Option A — Mark untrusted text, constrain the summary to plain text, and render untrusted text through one function that never shows an image

### Option B — Keep free Markdown, and filter the model's output for known exfiltration patterns

### Option C — Drop the summary feature and keep only the four-field suggestion

## Decision

Option A.

- The worker sends ticket text inside a spotlighting envelope (`relay.worker.untrusted.mark`): hidden
  characters removed, opening and closing markers with a nonce the author cannot predict, and imitation
  markers neutralized. The prompt says text inside the markers is data.
- A summary is plain text of at most 400 characters, with no address, link, image, markup or hidden
  character (`parse_summary`). One that fails is dropped and its reason kept with the job; the suggestion
  stays, and a person still confirms it (D3, ESC-N01).
- Text Relay did not write reaches the client only through `relay.render.render_text`: escaped, no image
  ever, and a clickable link only into Relay with no query string. `relay.api.suggestion_view` uses it and
  tells the reader what it removed.
- Lab 12.1's control matrix runs on every change to these controls under relay-coverage-gate-v1, and Gate
  G4 checks the same policy. Every attack class in the threat model's catalogue (relay-attack-classes
  2027.02.1) needs at least one verified control, and every exfiltration, unauthorized-action and
  persistence class needs two, in different modules. A control counts only if its probe shows it stops the
  class and still lets the matching legitimate case through. Marking never counts: it lowers how often a
  model obeys, which a probe cannot show.
- The gate verifies controls; it does not measure attack success rate. That needs a red-team exercise
  against the deployed model, which Relay has not yet run (owner aisha.r, by 2027-05-31).

## Consequences

- Marking lowers how often a model obeys; it does not stop it. The constraint on output and the renderer
  hold whether or not the model obeyed, which is why they are separate controls.
- A summary that quotes a customer's own address is dropped, which support staff will notice. tomas.b
  accepted that cost on 2027-02-08.
- The client must show the view's HTML as it is. A Markdown renderer run over it again would undo the
  image rule, so the client's change ships with a Content-Security-Policy that allows images from Relay
  only (carried to the service, Chapter 16).
- A steered suggestion is still possible. It is advice that a person confirms. How often a model is
  steered is unmeasured until the live red-team exercise.

## Rejected alternatives

### Option B — Keep free Markdown, and filter the model's output for known exfiltration patterns
Rejected because: a filter for known patterns misses encodings it has not seen, and the incident's image needed no pattern beyond an ordinary address.
Revisit if: never as the only control; a filter may be added in front of the renderer as an alert.

### Option C — Drop the summary feature and keep only the four-field suggestion
Rejected because: support staff asked to keep summaries after the pilot, and Option A removes the exfiltration path without removing the feature.
Revisit if: the live red-team exercise finds summaries steered often enough to mislead support staff.
