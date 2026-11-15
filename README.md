# Accountable Agents

**Engineering AI-Native Software from Specification to Production**

Book manuscript and hands-on labs. Every AI output is a proposal until evidence proves it.

## Repository layout

```
ai-dlc/
├── book/
│   ├── STYLE_GUIDE.md          ← the contract every chapter meets
│   ├── README.md               ← table of contents and chapter status
│   ├── chapters/               ← one Markdown file per chapter
│   ├── answers/                ← exercise answers and marking notes
│   └── reviews/                ← editor reviews and quality ratings per chapter
├── labs/
│   ├── README.md               ← how labs are organised and run
│   └── chNN/LN.M-<slug>/       ← one folder per lab (starter, solution, tests, data)
└── Accountable_Agents_Course_Outline_v2.2.docx   ← course outline
```

## Running the labs

Each lab is self-contained and needs Python 3.11+ and pytest.

```bash
cd labs/ch01/L1.1-value-stream-baseline
python -m pytest -q                        # tests against your work in starter/
LAB_TARGET=solution python -m pytest -q    # tests against the reference solution
```

PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q`, then `Remove-Item Env:LAB_TARGET`.

See [labs/README.md](labs/README.md) for conventions and [book/README.md](book/README.md) for chapter status.
