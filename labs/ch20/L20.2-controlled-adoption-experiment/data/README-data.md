# Lab 20.2 data (generated; do not edit)

Every file here is written by `scripts/generate_data.py` from a fixed seed. The data is synthetic.
The effects below were CONFIGURED into the generator. The readout recovers them with noise; it does
not discover them, and nothing here is evidence about real coding agents.

- `changes.csv`: one row per deployed change, Q4 2026 baseline and the 1 March to 28 May 2027 pilot.
- `assignments.csv`: the pilot teams' task assignments, made before the start from a fixed seed.
- `people.json`, `skills.json`, `survey.json` (team means only), `spend.json`, `config.json`.
- `prereg/`: the reviewed pre-registration and a sponsor's draft.

Configured effects (agent tasks against control tasks):

- agent_author_factor: {"S": 0.6, "M": 0.7, "L": 0.85}
- agent_review_factor: 1.3
- agent_review_wait_factor: 1.35
- pilot_team_queue_factor: 1.1
- fail_rate: {"control": 0.07, "agent": 0.09, "large_extra": 0.04}
- model_usd_per_agent_change: 12.0
- perceived_speedup_mean: 0.31

Skills and survey answers were configured with no difference between groups, apart from the
perceived-speedup question, which only the pilot teams were asked.
