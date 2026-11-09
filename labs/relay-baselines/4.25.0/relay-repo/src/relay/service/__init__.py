"""Relay's HTTP service (added in 4.19.0; ADR-007 and ADR-008; escalation routes in 4.20.0, ADR-009).

    python -m relay.service --db relay.db --demo --port 8080

The service depends on Relay's domain modules and on the public interface of
`relay.worker`. Nothing in the domain depends on it; `tests/test_architecture.py`
enforces both directions.
"""

from .app import RelayApp, job_view
from .directory import Directory, demo_directory, token_hash

__all__ = ["RelayApp", "job_view", "Directory", "demo_directory", "token_hash"]
