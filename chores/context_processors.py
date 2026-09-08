"""Template context processors for the chores app."""

from chores.auth import get_current_person


def current_person(request):
    """Expose the signed-in person to every template as ``current_person``."""
    return {"current_person": get_current_person(request)}
