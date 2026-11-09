"""Golden tests: every number Chapter 17 quotes from Lab 17.2. A change that moves one must fail here."""

from costlab.report import render_abuse, render_agents, render_caching, render_configs, render_gate, render_incident


def check(text, lines):
    for s in lines:
        assert s in text, s


def test_gate_view():
    check(render_gate(), [
        "| A: sim-large | 86.0% | n/a | n/a | n/a | n/a | $0.002510 |",
        "| B: sim-reasoner | 92.3% | +6.3 | +3.6 to +9.7 | 0 / 9 | 0.004 | $0.005916 |",
        "| C: routed | 90.5% | +4.5 | +2.3 to +7.3 | 0 / 6 | 0.031 | $0.005029 |",
        "Wrong first calls: 14.0% for A, 7.7% for B.", "Cost per correct, B against A: 2.36 times"])


def test_configurations():
    check(render_configs(), [
        "threshold 0.747956 (the highest catching 80% of hard dev tickets out of fold)",
        "| A: sim-large | 522 (87.0%) | 78 | 0 | 0 | 1.012 | $0.002158 | $0.002510 | 3.5 | 3.1 | 2.2 | 3.5 |",
        "| B: sim-reasoner | 540 (90.0%) | 40 | 20 | 101 | 1.135 | $0.005970 | $0.007529 | 12.9 | 12.5 | 5.4 | 26.6 |",
        "| C: routed | 545 (90.8%) | 55 | 0 | 0 | 1.003 | $0.004543 | $0.005018 | 10.5 | 10.2 | 4.2 | 10.6 |",
        "C sends 65.5% of runs to sim-reasoner.",
        "| B: sim-reasoner | +3.0 | -0.3 to +6.9 | 5 / 8 | 0.581 | 3.00 times |",
        "| C: routed | +3.8 | +1.7 to +6.6 | 0 / 6 | 0.031 | 2.00 times |",
        "A: sim-large 13.0%, B: sim-reasoner 6.9%, C: routed 9.2%.",
        "60 s / exactly 60 s: A: sim-large 0 / 0, B: sim-reasoner 0 / 20, C: routed 0 / 0.",
        "B's route: a call allowed 2048 output tokens can take 49.3 s, past the 10 s timeout",
        "Route check, C's hard route (p99 time to first token before reasoning 3.8 s): no problem."])


def test_incident():
    check(render_incident(), [
        "Tickets per day, Monday to Sunday: 1,354, 1,338, 1,301, 1,280, 1,330, 340, 343.",
        "Full days on the new model: 33 (2027-01-07 to 2027-02-08), 33,791 tickets.",
        "$228.96 on sim-reasoner, against $73.78 on sim-large (3.10 times; $155.18 more).",
        "about 1,126.", "Cost per call, new against old: 2.77 times.",
        "(no labels needed; baseline A $0.002183, tolerance 25%, three-day window) would first have alerted on "
        "2027-01-07, at $0.003724 per suggestion.",
        "would also have alerted on 2027-01-07, at $0.004186."])


def test_caching():
    check(render_caching(), [
        "Calls: one per ticket, 7,586 in the week.",
        "| 427 | 0 | 0 | 7,586 | 0.0% | $12.96 | $12.96 |",
        "| 1,200 | 322 | 7,264 | 0 | 95.8% | $36.41 | $3.68 |",
        "| 4,000 | 322 | 7,264 | 0 | 95.8% | $121.38 | $12.25 |",
        "hits 82.5% of the time on sim-large and 92.3% on sim-reasoner",
        "(600 triages) costs $2.74; at an assumed 50% batch discount, $1.37."])


def test_abuse():
    check(render_abuse(), [
        "Each queued ticket reserves $0.023824", "C's mean cost per ticket, $0.004558;",
        "| one-token | no | 36,000 | 36,000 | 139 | 139 | n/a | $860.98 | $164.74 | $2,582.93 | 0 |",
        "| one-token | yes | 36,000 | 125 | 139 | 139 | 12.6 | $6.29 | $1.20 | $18.87 | 35,875 |",
        "| twenty-tokens | yes | 36,000 | 2,500 | 140 | 18 | 250.1 | $59.99 | $11.48 | $179.97 | 33,622 |",
        "all 3 attempts, $0.071472 a ticket.", "buys 125 tickets at one call's ceiling; at C's mean cost it would pay "
        "for 658."])


def test_agents():
    check(render_agents(), [
        "| workflow | 270 | 170 | $0.095 | $0.151 | $0.161 | $0.189 | $0.30 | $0.30 |",
        "| single | 270 | 186 | $0.142 | $0.206 | $0.225 | $0.718 | $0.40 | $0.45 |",
        "| multi | 270 | 189 | $0.243 | $0.347 | $0.386 | $0.736 | $0.65 | $0.70 |",
        "| routed | 270 | 197 | $0.168 | $0.231 | $0.249 | $0.432 | $0.55 | $0.60 |"])
