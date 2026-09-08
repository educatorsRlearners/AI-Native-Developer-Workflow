"""Create the two household members.

Names and emails are read from CLI arguments or, if omitted, environment
variables:

    SEED_PERSON_1_NAME / SEED_PERSON_1_EMAIL
    SEED_PERSON_2_NAME / SEED_PERSON_2_EMAIL

The command is idempotent: people are matched by email, so running it twice
leaves exactly two rows. It never overwrites an existing person's ``pin_hash``
and never sets a usable PIN (PIN setup is issue #7) -- new rows get an unusable
placeholder hash.
"""

import os

from django.core.management.base import BaseCommand, CommandError

from chores.models import Person

UNUSABLE_PIN_HASH = "!"

DEFAULTS = [
    ("SEED_PERSON_1_NAME", "SEED_PERSON_1_EMAIL", "Alex", "alex@example.com"),
    ("SEED_PERSON_2_NAME", "SEED_PERSON_2_EMAIL", "Sam", "sam@example.com"),
]


class Command(BaseCommand):
    help = "Create the two household members (idempotent, matched by email)."

    def add_arguments(self, parser):
        parser.add_argument("--person1-name")
        parser.add_argument("--person1-email")
        parser.add_argument("--person2-name")
        parser.add_argument("--person2-email")

    def handle(self, *args, **options):
        people = [
            (
                options["person1_name"] or os.environ.get(DEFAULTS[0][0], DEFAULTS[0][2]),
                options["person1_email"] or os.environ.get(DEFAULTS[0][1], DEFAULTS[0][3]),
            ),
            (
                options["person2_name"] or os.environ.get(DEFAULTS[1][0], DEFAULTS[1][2]),
                options["person2_email"] or os.environ.get(DEFAULTS[1][1], DEFAULTS[1][3]),
            ),
        ]

        emails = [email for _, email in people]
        if len(set(emails)) != len(emails):
            raise CommandError("The two people must have distinct emails.")

        for name, email in people:
            person, created = Person.objects.get_or_create(
                email=email,
                defaults={"name": name, "pin_hash": UNUSABLE_PIN_HASH},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created {name} <{email}>"))
            else:
                self.stdout.write(f"Exists, left unchanged: {person.name} <{email}>")
