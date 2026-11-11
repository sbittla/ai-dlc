"""Fixture stand-in for the AI step, with its fallback."""


def summarize(text, model=None):
    return text[:200] if model is None else model(text)
