# Accountable Agents — companion code

**Engineering AI-Native Software from Specification to Production**

Hands-on labs and exercise answers for the book *Accountable Agents*. Every AI output is a proposal until evidence proves it.

## Repository layout

```
ai-dlc/
├── labs/
│   ├── README.md               ← how labs are organised and run, with the lab index
│   ├── relay-baselines/        ← Relay repository snapshots the labs start from
│   └── chNN/LN.M-<slug>/       ← one folder per lab (starter, solution, tests, data)
├── book/
│   └── answers/                ← exercise answers and marking notes, one file per chapter
└── .github/workflows/labs.yml  ← CI: every lab's reference solution on Linux and Windows
```

## Running the labs

Each lab is self-contained. Labs run offline at no cost and need Python 3.11+ and pytest.

```bash
cd labs/ch01/L1.1-value-stream-baseline
python -m pytest -q                        # tests against your work in starter/
LAB_TARGET=solution python -m pytest -q    # tests against the reference solution
```

PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q`, then `Remove-Item Env:LAB_TARGET`.

See [labs/README.md](labs/README.md) for conventions and the full lab index, and [book/answers/](book/answers/) for exercise answers.
