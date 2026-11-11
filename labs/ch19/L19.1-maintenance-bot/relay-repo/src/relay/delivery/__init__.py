"""Delivery adapters: what carries the escalation engine's outbox across Relay's network boundary (4.26.0).

ADR-007 promised that each integration point would arrive as one module with its own ADR, and that the
architecture test would admit exactly that module to the network (FF004 in Lab 6.2; AR4 here). This
package holds those modules. `ADAPTERS` maps each one to its ADR, and `tests/test_architecture.py`
checks that the modules allowed to import network packages outside the service are exactly these.

    relay.delivery.email_smtp   ADR-033   email for escalations, summaries and rule notices

Webhook delivery is not here yet: it needs the webhook secret in the worker's configuration, which the
deployment does not supply (Chapter 13 carried it).

Nothing in an adapter chooses who receives a message. The engine names a Relay user; the adapter looks
the address up in Relay's directory and refuses a message it cannot resolve that way.
"""

from .email_smtp import (ACCEPTED_KINDS, Delivery, EmailAdapter, RecordingTransport, SmtpTransport,
                         Transport)

ADAPTERS = {"relay.delivery.email_smtp": "ADR-033"}

__all__ = ["ACCEPTED_KINDS", "ADAPTERS", "Delivery", "EmailAdapter", "RecordingTransport", "SmtpTransport",
           "Transport"]
