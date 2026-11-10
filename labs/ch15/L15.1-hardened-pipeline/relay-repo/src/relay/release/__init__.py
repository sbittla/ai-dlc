"""Release controls that live in Relay's own code (added in 4.29.0; ADR-047, ADR-048).

- `flags`: feature flags and kill switches for AI features. An AI feature is off unless its flag says
  otherwise, a tripped kill switch beats every rollout setting, and anything malformed means off (ADR-047).
- `judged`: the evaluation gate's rule for judge-injection items. Their release verdict is a person's label;
  a judge's verdict on them is recorded and never read, and a missing label stops the gate (ADR-048).

Standard library only, no network (`tests/test_release_architecture.py`).
"""

from .flags import FlagError, FlagSet, KillStore
from .judged import GradedItem, MissingHumanLabel, needs_person, release_verdicts

__all__ = ["FlagError", "FlagSet", "KillStore", "GradedItem", "MissingHumanLabel", "needs_person",
           "release_verdicts"]
