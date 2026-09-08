"""Nag notification delivery.

``send_nag_email(person, chores)`` sends exactly one plain-text + HTML digest
email to one person listing the chores it was handed. It does not decide who is
overdue or when to run - the nightly sweep (#12) works that out and calls this
function with a list that is already exactly the person's overdue chores.

Stateless and clock-free: no DB writes, no "sent today" tracking, no
``timezone.now()`` branching. Next-due dates are computed for display only.

Imports are limited to ``chores.models``, ``chores.services``,
``chores.recurrence``, ``django.core.mail``, ``django.template``,
``django.conf`` and ``logging``.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from chores import recurrence, services

logger = logging.getLogger(__name__)


def _next_due_for_display(chore):
    """Next-due date for one chore, for display only.

    Computed from the chore's latest completion via ``recurrence.next_due``. A
    chore with no completions shows its ``anchor_date`` (``next_due`` returns the
    anchor when ``last_completed is None``).
    """
    last_completed = services.last_completed_on(chore)
    return recurrence.next_due(
        chore.cadence,
        chore.anchor_date,
        last_completed,
        custom_interval_days=chore.custom_interval_days,
    )


def send_nag_email(person, chores):
    """Send one digest email to ``person`` listing ``chores``.

    ``person`` is a ``Person``; ``chores`` is an iterable of ``Chore``. Emails
    precisely the chores it is given, in the order given - it runs no recurrence
    filtering and no overdue check of its own.

    - Empty ``chores``: send nothing, log one debug line, return normally.
    - ``person.email`` empty/falsy: send nothing, log one warning naming the
      person, return normally.
    - SMTP failure: the backend exception propagates to the caller (no retry,
      no swallowing).
    """
    chores = list(chores)

    if not chores:
        logger.debug("send_nag_email: no chores for %s, nothing to send", person)
        return

    if not person.email:
        logger.warning(
            "send_nag_email: person %s has no email address, skipping", person
        )
        return

    count = len(chores)
    if count == 1:
        subject = "1 chore needs doing"
    else:
        subject = f"{count} chores need doing"

    context = {
        "person": person,
        "chores": [
            {"title": chore.title, "next_due": _next_due_for_display(chore)}
            for chore in chores
        ],
        "time_zone": settings.TIME_ZONE,
    }

    text_body = render_to_string("email/nag_email.txt", context)
    html_body = render_to_string("email/nag_email.html", context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[person.email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send()
