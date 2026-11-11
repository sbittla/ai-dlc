# Relay's service level objectives

Owner: sam.o, with lena.k for the AI-quality objective and aisha.r for the safety objective. ADR-037.
Machine-readable definitions: `slos.json` (relay-slo-v1). Budget policy: `budget-policy.md`.

| SLO | SLI (good events) | Target, 30 days | Alerting |
| --- | --- | ---: | --- |
| SLO-API-AVAIL | `/v1` responses below 500 | 99.9% | workbook burn-rate table |
| SLO-API-LATENCY | `/v1` responses below 500 within 250 ms | 99% | workbook burn-rate table |
| SLO-TRIAGE-FRESH | triage jobs answered within 60 s | 99% | workbook burn-rate table |
| SLO-TRIAGE-QUALITY | confirmed suggestions kept unchanged | 80% | ticket: 7-day and 1-day windows at 1.5x |
| SLO-TRIAGE-SAFETY | outputs that pass the output check | 99.5% | ticket: 7-day and 1-day windows at 1.5x |

Why these. Each SLI counts something a customer or a support engineer would call good or bad. 4xx answers
count as good for availability: the server did what it promised, and a burst of 401s is a security signal
(SD-001), not an outage. The latency threshold is a bucket boundary of the duration histogram, so the SLI is
exact. The AI objectives use labels that arrive slowly and in tens a day, so they open tickets, never pages,
and need 100 labelled events in the window before they fire.

The escalation evaluator is not an SLO here. ESC-N09 asks for a page after 5 minutes without a completed pass
(AL-001) and for 95% of steps within 60 seconds each week (RF-001), and both are checked directly.

Lab 16.1 checks the policy against 30 days of generated traffic and compares it with a static threshold and
a single window.
