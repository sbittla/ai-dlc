"""Power for four candidate designs, by simulation (Chapter 20, Section 20.5; Chapter 7's statistical power).

The outcome is log change lead time. The model behind every design is

    y = mu + team + engineer + team-by-period drift + effect * treated + heterogeneity + residual

with standard deviations estimated from the baseline quarter where the data allows (`variance_components`), and
stated as assumptions where it does not (`ASSUMPTIONS`): a single quarter cannot show how much each team's lead
time drifts from one quarter to the next, or how much the effect varies between engineers.

Designs (DESIGNS):
  D1  team-level: two pilot teams against two comparison teams, before and after (difference in differences).
  D2  engineer-level: half the engineers of each of the four teams randomized to agents for the whole pilot.
  D3  task-level within the two pilot teams: each task randomized to agent or control, analyzed within engineer.
  D4  task-level within all four teams.

Each simulated pilot is analyzed the way the design would be analyzed for real, with a t-test on the units that
were randomized (teams, engineers, or engineers' within-person differences; task-level designs can also use the
exact sign test), and power is the share of
simulated pilots whose two-sided test rejects at alpha. Simulating at the level of team and engineer means,
not individual changes, keeps this fast; the means are drawn with the variance the changes would give them.
"""

from __future__ import annotations

import math
import random
from functools import lru_cache

from .stats import binom_two_sided, t_quantile

PILOT_TEAMS = ("integrations", "analytics")
COMPARISON_TEAMS = ("mobile", "marketplace")

DESIGNS = {
    "D1": {"name": "team level, 2 pilot vs 2 comparison teams, before and after", "unit": "team",
           "teams": PILOT_TEAMS + COMPARISON_TEAMS},
    "D2": {"name": "engineer level, half of each team on agents", "unit": "engineer",
           "teams": PILOT_TEAMS + COMPARISON_TEAMS},
    "D3": {"name": "task level within the two pilot teams", "unit": "task (analyzed within engineer)",
           "teams": PILOT_TEAMS},
    "D4": {"name": "task level within all four teams", "unit": "task (analyzed within engineer)",
           "teams": PILOT_TEAMS + COMPARISON_TEAMS},
}

# Stated assumptions: not estimable from one baseline quarter.
ASSUMPTIONS = {
    "sd_team_period": 0.10,      # each team's quarter-to-quarter drift in log lead time
    "sd_heterogeneity": 0.10,    # how much the agent effect varies between engineers (log scale)
    "contamination_engineer": 0.30,  # share of the effect reaching control engineers in D2 (shared code, review)
    "contamination_task": 0.20,      # share of the effect reaching control tasks in D3/D4 (habits, code, queue)
    "changes_per_engineer_week": 1.92,  # measured in the Q4 2026 baseline (850 changes, 34 engineers, 13 weeks)
}


def variance_components(rows: list[dict], outcome: str = "lead_time_hours") -> dict:
    """Method-of-moments estimates of team, engineer and residual standard deviations of log outcome (provided).

    rows: baseline changes. Returns sd_team, sd_engineer, sd_residual and the counts behind them. With four teams
    the team estimate is rough, and the text says so.
    """
    by_eng: dict[str, list[float]] = {}
    team_of: dict[str, str] = {}
    for r in rows:
        by_eng.setdefault(r["engineer"], []).append(math.log(r[outcome]))
        team_of[r["engineer"]] = r["team"]
    # residual: pooled within-engineer variance
    ss, dof = 0.0, 0
    eng_mean = {}
    for e, ys in by_eng.items():
        m = sum(ys) / len(ys)
        eng_mean[e] = m
        ss += sum((y - m) ** 2 for y in ys)
        dof += len(ys) - 1
    var_r = ss / dof
    n_bar = sum(len(v) for v in by_eng.values()) / len(by_eng)
    # engineer: variance of engineer means within team, minus the residual's share
    teams: dict[str, list[str]] = {}
    for e, t in team_of.items():
        teams.setdefault(t, []).append(e)
    ss_e, dof_e = 0.0, 0
    team_mean = {}
    for t, es in teams.items():
        m = sum(eng_mean[e] for e in es) / len(es)
        team_mean[t] = m
        ss_e += sum((eng_mean[e] - m) ** 2 for e in es)
        dof_e += len(es) - 1
    var_e = max(0.0, ss_e / dof_e - var_r / n_bar)
    m_bar = len(by_eng) / len(teams)
    grand = sum(team_mean.values()) / len(team_mean)
    var_tm = sum((m - grand) ** 2 for m in team_mean.values()) / (len(team_mean) - 1)
    var_t = max(0.0, var_tm - var_e / m_bar - var_r / (n_bar * m_bar))
    return {"sd_team": math.sqrt(var_t), "sd_engineer": math.sqrt(var_e), "sd_residual": math.sqrt(var_r),
            "changes": sum(len(v) for v in by_eng.values()), "engineers": len(by_eng), "teams": len(teams)}


@lru_cache(maxsize=None)
def t_crit(df: int, alpha: float = 0.05) -> float:
    return t_quantile(1 - alpha / 2, df)


def _poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _t_stat(diffs: list[float]) -> tuple[float, int]:
    n = len(diffs)
    m = sum(diffs) / n
    var = sum((d - m) ** 2 for d in diffs) / (n - 1)
    return (m / math.sqrt(var / n) if var > 0 else math.inf), n - 1


def _two_sample_t(a: list[float], b: list[float]) -> tuple[float, int]:
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    ss = sum((x - ma) ** 2 for x in a) + sum((x - mb) ** 2 for x in b)
    df = len(a) + len(b) - 2
    sp2 = ss / df
    se = math.sqrt(sp2 * (1 / len(a) + 1 / len(b)))
    return (ma - mb) / se if se > 0 else math.inf, df


def one_pilot_team_level(rng, comps, a, effect, team_sizes, weeks):
    """D1 (provided, a worked example): one simulated pilot, analyzed as a difference in differences of team means."""
    lam = a["changes_per_engineer_week"] * weeks
    diffs = {}
    for team, size in team_sizes.items():
        n_pre = sum(_poisson(rng, lam) for _ in range(size))
        n_post = sum(_poisson(rng, lam) for _ in range(size))
        noise = comps["sd_residual"] * math.sqrt(1 / n_pre + 1 / n_post)
        drift = rng.gauss(0, a["sd_team_period"]) - rng.gauss(0, a["sd_team_period"])
        treated = team in PILOT_TEAMS
        het = rng.gauss(0, a["sd_heterogeneity"] / math.sqrt(size)) if treated else 0.0
        diffs[team] = (effect if treated else 0.0) + het + drift + rng.gauss(0, noise)
    pilot = [diffs[t] for t in team_sizes if t in PILOT_TEAMS]
    comp = [diffs[t] for t in team_sizes if t not in PILOT_TEAMS]
    return _two_sample_t(pilot, comp)


def one_pilot_engineer_level(rng, comps, a, effect, team_sizes, weeks):
    """D2 (provided, a worked example): engineers randomized within team; t-test on engineer means, team-centred."""
    lam = a["changes_per_engineer_week"] * weeks
    treated, control = [], []
    for team, size in team_sizes.items():
        tm = []
        n_t = size // 2 + (size % 2 and rng.random() < 0.5)
        for i in range(size):
            n = max(1, _poisson(rng, lam))
            on = i < n_t
            mean = rng.gauss(0, comps["sd_engineer"]) + rng.gauss(0, comps["sd_residual"] / math.sqrt(n))
            mean += effect + rng.gauss(0, a["sd_heterogeneity"]) if on else a["contamination_engineer"] * effect
            tm.append((on, mean))
        centre = sum(m for _, m in tm) / len(tm)  # the team effect and drift are shared, so centring removes them
        treated += [m - centre for on, m in tm if on]
        control += [m - centre for on, m in tm if not on]
    t, df = _two_sample_t(treated, control)
    return t, df - (len(team_sizes) - 1)  # one degree of freedom spent on each team's centre beyond the first


def task_level_differences(rng, comps, a, effect, team_sizes, weeks) -> list[float]:
    """D3 and D4: tasks randomized within engineer. Return each engineer's within-person difference.

    For each engineer: draw the number of changes (Poisson, mean changes_per_engineer_week * weeks) and how many
    fall in the agent arm (half on average); skip an engineer with no change in either arm. The engineer's
    difference (agent minus control) is effect * (1 - contamination_task) + heterogeneity + noise, where the
    noise has standard deviation sd_residual * sqrt(1/n_agent + 1/n_control). Team and engineer effects cancel
    within the person.

    Draw in this order, so that results match the golden values: for each team in team_sizes, for each engineer,
    n = _poisson(rng, lam); then one rng.random() < 0.5 per change for the agent arm; skip the engineer if either
    arm is empty; then rng.gauss(0, sd_heterogeneity); then rng.gauss(0, noise sd).
    """
    raise NotImplementedError("TODO 1: implement task_level_differences")


RUNNERS = {"D1": one_pilot_team_level, "D2": one_pilot_engineer_level}
TESTS = ("t", "sign")


def simulate_power(design: str, comps: dict, team_sizes: dict, effect_ratio: float, weeks: int = 13,
                   reps: int = 1000, seed: int = 20270226, alpha: float = 0.05,
                   assumptions: dict | None = None, test: str = "t") -> float:
    """Share of `reps` simulated pilots of `design` whose two-sided test rejects at `alpha`.

    effect_ratio is the true ratio of lead times (agent over control), for example 0.80 for 20% shorter.
    team_sizes maps every team to its number of engineers; only the design's teams take part.
    test: "t" (the t-test each design uses) or "sign" (the exact sign test over engineers' differences; task-level
    designs only). Power belongs to a test, so a registration's power must be computed for its registered test.
    """
    if test not in TESTS or (test == "sign" and design in RUNNERS):
        raise ValueError(f"test {test!r} is not available for design {design}")
    a = dict(ASSUMPTIONS, **(assumptions or {}))
    sizes = {t: team_sizes[t] for t in DESIGNS[design]["teams"]}
    rng = random.Random(f"{seed}:{design}:{effect_ratio}:{weeks}:{sorted(a.items())}")
    effect = math.log(effect_ratio)
    hits = 0
    for _ in range(reps):
        if design in RUNNERS:
            t, df = RUNNERS[design](rng, comps, a, effect, sizes, weeks)
            hits += df >= 1 and abs(t) > t_crit(df, alpha)
            continue
        diffs = task_level_differences(rng, comps, a, effect, sizes, weeks)
        if test == "sign":
            pos = sum(1 for d in diffs if d > 0)
            neg = sum(1 for d in diffs if d < 0)
            hits += binom_two_sided(pos, neg) < alpha
        else:
            t, df = _t_stat(diffs)
            hits += df >= 1 and abs(t) > t_crit(df, alpha)
    return hits / reps


def weeks_for_power(design: str, comps: dict, team_sizes: dict, effect_ratio: float, target: float = 0.80,
                    max_weeks: int = 52, reps: int = 1000, seed: int = 20270226, test: str = "t") -> int | None:
    """The fewest whole weeks at which simulate_power reaches `target`, or None within max_weeks."""
    for weeks in range(4, max_weeks + 1):
        if simulate_power(design, comps, team_sizes, effect_ratio, weeks, reps, seed, test=test) >= target:
            return weeks
    return None
