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
