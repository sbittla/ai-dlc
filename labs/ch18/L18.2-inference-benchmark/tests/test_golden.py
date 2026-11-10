"""Golden tests: every number Chapter 18 quotes from Lab 18.2. All but the last test come from the SIMULATED
serving model; the last reads the real run recorded on the author's laptop (data/measured/)."""

from servelab.report import render_memory, render_plan, render_real, render_sweep


def test_memory():
    t = render_memory()
    for s in ("| fp16 | 3.00 | 28,672 | 648,716 | 82.0% |", "| int8 | 1.50 | 28,672 | 701,032 | 81.5% |",
              "| int4 | 0.75 | 28,672 | 727,190 | 79.0% |", "| 1 | 12.1 | 83 | 83 |", "| 8 | 12.6 | 80 | 637 |",
              "| 32 | 14.2 | 70 | 2,246 |", "| 64 | 16.5 | 61 | 3,880 |"):
        assert s in t, s


def test_sweep():
    t = render_sweep()
    for s in ("| fp16 | static | 2 | 123.2 | 0.897 | 1.185 | 2.201 | yes |",
              "| fp16 | static | 8 | 445.8 | 1.188 | 2.019 | 3.139 | no |",
              "| fp16 | static | 16 | 567.4 | 11.495 | 22.686 | 23.834 | no |",
              "| fp16 | continuous | 8 | 455.5 | 0.045 | 0.105 | 1.599 | yes |",
              "| fp16 | continuous | 16 | 902.3 | 0.071 | 0.170 | 2.839 | yes |",
              "| fp16 | continuous | 32 | 1,208.8 | 5.465 | 9.595 | 12.310 | no |",
              "| int4 | static | 16 | 898.7 | 0.777 | 1.235 | 1.690 | yes |",
              "| int4 | continuous | 32 | 1,877.4 | 0.084 | 0.416 | 2.723 | yes |"):
        assert s in t, s


def test_plan():
    t = render_plan()
    for s in ("| fp16, static | 2 | 0.530 | 26.5% | 2 | $1,168.00 | $67.99 | 17.2 | never | - |",
              "| fp16, continuous | 16 | 0.530 | 3.3% | 2 | $1,168.00 | $67.99 | 17.2 | 535,044 | 2 |",
              "| int4, continuous | 32 | 0.530 | 1.7% | 2 | $1,168.00 | $67.99 | 17.2 | 535,044 | 2 |",
              "fp16, static: one accelerator at full use costs $0.004969 a ticket (API $0.002183).",
              "fp16, continuous: one accelerator at full use costs $0.000621 a ticket (API $0.002183).",
              "Relay's triage volume: 31,146 tickets a month; outage peak 0.530 requests a second."):
        assert s in t, s


def test_recorded_real_run():
    t = render_real()
    for s in ("Recorded (author's laptop): HuggingFaceTB/SmolLM2-135M-Instruct at 12fd25f77366, SHA-256 verified",
              "median time to first token 0.362 s, 12.2 output tokens/s.",
              "183 tokens in 5.947 s, 30.8 tokens/s (2.5 times the sequential rate)."):
        assert s in t, s
