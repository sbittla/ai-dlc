"""Relay's notification preferences (4.22.0, PR notify-1; ADR-018).

notify-1 imports the legacy module unchanged and re-exports its functions, so
callers keep their names while the characterization tests are written. Later
pull requests replace what is underneath; nothing here changes behaviour.
"""

from .legacy import SPAM_DAYS, TYPES, clear_spam, get_prefs, init, mark_spam, mute, should_send

__all__ = ["SPAM_DAYS", "TYPES", "clear_spam", "get_prefs", "init", "mark_spam", "mute", "should_send"]
