# Labs

Every lab follows the same layout, so you always know where things are.

```
labs/chNN/LN.M-<slug>/
├── README.md          ← brief, steps, expected evidence, sample evidence, troubleshooting, cleanup, rubric
├── pyproject.toml     ← pytest configuration (and pinned dependencies, if any)
├── data/              ← input data; generated deterministically and committed
├── scripts/           ← generators and helpers (how the data was made)
├── starter/           ← YOUR WORK: code with TODOs that the tests specify
├── solution/          ← reference solution (instructors; read only after finishing)
├── templates/         ← documents you copy into evidence/ and complete
├── tests/             ← specification tests; run against starter/ by default
└── evidence/          ← YOUR DELIVERABLES (git-ignored except .gitkeep)
```

## Conventions

- **Tests are the specification.** Small hand-computed fixtures define each behaviour; dataset tests check your numbers against the reference.
- **CI.** `.github/workflows/labs.yml` runs every lab's reference solution on Linux and Windows and checks that generated data reproduces exactly.
- **Two targets.** `python -m pytest` grades `starter/`. `LAB_TARGET=solution python -m pytest` checks the reference. Instructor CI runs the solution for every lab on every change.
- **Starter code fails only on TODOs.** Everything else (loading, reporting, CLI) is provided and runs.
- **Deterministic data.** Generators use fixed seeds; regenerate with `python scripts/generate_data.py`.
- **Standard library first.** Labs that need packages pin them in `pyproject.toml` and say so at the top of their README.
- **Cost ceilings.** Each README states the maximum cloud or model spend. Local labs cost $0.
- **AI-use disclosure.** You may use coding agents in any lab. Every evidence template asks what an agent produced and how you verified it.
- **Safe scope.** Offensive security labs run only against your own lab instances.

## Index

| Lab | Title | Type | Time |
| --- | --- | --- | --- |
| [L1.1](ch01/L1.1-value-stream-baseline/) | Value-stream map and baseline metrics | Core | 3 h |
| [L1.2](ch01/L1.2-productivity-claim-audit/) | Audit a vendor productivity claim | Stretch | 2 h |
| [L2.1](ch02/L2.1-model-eval-harness/) | A model evaluation harness | Core | 4 h |
| [L2.2](ch02/L2.2-context-strategies/) | One question set, five context strategies | Stretch | 3 h |
| [L3.1](ch03/L3.1-accountable-workspace/) | Sandboxed agent workspace and a first agent-built PR | Core | 4 h |
| [L3.2](ch03/L3.2-constrained-mcp-server/) | Constrained MCP server and workspace threat model | Stretch | 4 h |
| [L4.1](ch04/L4.1-brief-to-prd/) | Ambiguous brief to PRD, NFRs (including security) and traceability | Core | 3 h |
| [L4.2](ch04/L4.2-ambiguity-eval/) | An eval that finds seeded requirement ambiguities | Stretch | 2 h |
| [L5.1](ch05/L5.1-spec-first-delivery/) | Spec-first feature delivery | Core | 4 h |
| [L5.2](ch05/L5.2-spec-drift-check/) | Spec drift check in CI | Stretch | 3 h |
| [L6.1](ch06/L6.1-architecture-options-adr/) | Two architectures, scored, with ADRs and a threat model | Core | 3 h |
| [L6.2](ch06/L6.2-fitness-functions-ci/) | Fitness functions in CI | Stretch | 3 h |
| [L7.1](ch07/L7.1-triage-eval-gate/) | Triage eval suite and CI gate | Core | 4 h |
| [L7.2](ch07/L7.2-judge-calibration/) | Calibrate an LLM judge against human labels | Stretch | 3 h |
| [L8.1](ch08/L8.1-test-first-agent/) | Test-first feature with an agent | Core | 4 h |
| [L8.2](ch08/L8.2-mutation-property-repair/) | Mutation and property-based test repair | Stretch | 4 h |
| [L9.1](ch09/L9.1-spec-to-reviewed-pr/) | Feature from approved spec to reviewed pull request, with migration, API and docs | Core | 5 h |
| [L9.2](ch09/L9.2-legacy-refactor-characterization/) | Legacy refactor with characterization tests and parallel agents | Stretch | 4 h |
| [L10.1](ch10/L10.1-workflow-agent-multiagent/) | Same task as workflow, single agent and multi-agent, compared on success, cost and latency | Core | 5 h |
| [L10.2](ch10/L10.2-failure-injection-approval-gates/) | Failure injection, approval gates and recovery | Stretch | 3 h |
| [L11.1](ch11/L11.1-guardrailed-cloud-environment/) | Guardrailed, budget-capped cloud environment with IaC | Core | 5 h |
| [L11.2](ch11/L11.2-azure-gcp-mapping/) | Azure and GCP mapping with cost comparison | Stretch | 2 h |
| [L12.1](ch12/L12.1-agentic-red-team/) | Threat model and defence verification: a control matrix on Relay's own artefacts, coverage by failure domain, and the coverage gate for Gate G4 | Core | 5 h |
| [L12.2](ch12/L12.2-malicious-mcp-server/) | A malicious MCP server: whole-definition pins, allowlisting with a launch-time source hash, name collisions and scope review, and the shadowing case no check catches | Stretch | 4 h |
| [L13.1](ch13/L13.1-secure-agent-loop/) | Secure the agent loop: gates, a dependency gate, fix re-verification, catch rate and release evidence | Core | 4 h |
| [L13.2](ch13/L13.2-poisoned-instructions-ci-injection/) | Poisoned instruction files and CI prompt injection via an issue comment | Stretch | 4 h |
| [L14.1](ch14/L14.1-agent-identity-kill-switch/) | Agent identity, an anomaly detection rule and a kill-switch drill | Core | 4 h |
| [L14.2](ch14/L14.2-governance-pack/) | Governance pack: permission matrix, DPIA, licence scan, EU AI Act classification | Stretch | 3 h |
| [L15.1](ch15/L15.1-hardened-pipeline/) | Hardened pipeline: workflow lint, a pipeline guard, fail-closed gates, signature-verified admission and Gate G4's adversarial row with deployment evidence | Core | 5 h |
| [L15.2](ch15/L15.2-canary-kill-switch/) | Canary release with automatic rollback on SLO burn, and an AI-feature kill switch tripped by a cohort test | Stretch | 4 h |
| [L16.1](ch16/L16.1-otel-redaction-slo/) | OpenTelemetry instrumentation with PII redaction, an SLO and a multi-window burn-rate alert | Core | 4 h |
| [L16.2](ch16/L16.2-game-day-postmortem/) | Combined reliability and security game day: cited hypotheses, a remediation gate and a blameless postmortem | Stretch | 4 h |
| [L17.1](ch17/L17.1-load-test-bottleneck/) | Load-test baseline, bottleneck, fix and re-measure: workload model, open schedule, percentiles with intervals, limiter fix, soak and worker capacity | Core | 4 h |
| [L17.2](ch17/L17.2-cost-per-success-routing/) | Cost per successful task across routing and caching configurations, plus spend quotas under an abuse burst | Stretch | 3 h |
| [L18.1](ch18/L18.1-durable-sandboxed-workers/) | Durable, sandboxed agent workers: business keys, fenced leases, a dead-letter state, an effect ledger, a code sandbox with escape attempts, workload identity, and fault injection for restart, duplicate, timeout, rate limit, kill switch and cancellation, traced end to end | Core | 5 h |
| [L18.2](ch18/L18.2-inference-benchmark/) | Inference benchmark: KV-cache memory, prefill and decode, static against continuous batching and quantization on a simulated serving model, a capacity plan against the managed API, and an optional real run of a small open-weight model | Stretch | 3 h |
| [L19.1](ch19/L19.1-maintenance-bot/) | A maintenance bot for dependency and vulnerability fixes: structured triage, mirror-only plans, reproduction and pinned defaults in the sandbox, an evidence bundle, approvals that refuse the bot and its owner, a guard metric with rollback, and a paired replay of two policies | Core | 4 h |
| [L19.2](ch19/L19.2-safety-security-case/) | A safety and security case for the maintenance bot, checked against fifteen inert adversarial records and six budget, cancellation and crash scenarios | Stretch | 3 h |
| [L20.1](ch20/L20.1-maturity-operating-model-roi/) | Maturity assessment from evidence, a target operating model, an approved tool and MCP catalogue with an acceptable-use policy checked against Relay's pins and registry, and an ROI model that keeps measured and projected inputs apart, with a tornado | Core | 3 h |
| [L20.2](ch20/L20.2-controlled-adoption-experiment/) | A controlled adoption experiment: variance components from a baseline, power of four designs by simulation, a frozen pre-registration checked against eleven rules, and a within-engineer readout with a paired t-test and an exact sign test | Stretch | 3 h |
