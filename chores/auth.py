"""Resolving and requiring the current signed-in person.

Sign-in is by name + numeric PIN (see :mod:`chores.views`). The signed-in
person's id lives in ``request.session["person_id"]``; this module turns that
back into a :class:`~chores.models.Person` and gates views that need one.
"""

from functools import wraps

from django.shortcuts import redirect
from django.urls import reverse

from chores.models import Person


def get_current_person(request):
    """Return the signed-in :class:`Person` for ``request`` or ``None``.

    Reads ``request.session["person_id"]``. Returns ``None`` (never raises)
    when the key is missing or points at a person that no longer exists. The
    result is cached on ``request._current_person`` so repeated calls in one
    request hit the database at most once.
    """
    cached = getattr(request, "_current_person", False)
    if cached is not False:
        return cached

    person_id = request.session.get("person_id")
    person = None
    if person_id is not None:
        person = Person.objects.filter(pk=person_id).first()

    request._current_person = person
    return person


def require_person(view_func):
    """Redirect to the sign-in page when there is no current person.

    On an unauthenticated request returns a 302 to
    ``chores:login?next=<current full path>``; otherwise calls ``view_func``
    unchanged.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if get_current_person(request) is None:
            login_url = reverse("chores:login")
            return redirect(f"{login_url}?next={request.get_full_path()}")
        return view_func(request, *args, **kwargs)

    return _wrapped
