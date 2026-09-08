"""Set (or reset) a person's sign-in PIN.

    manage.py set_pin <email>

Looks the person up by email, prompts for the PIN twice with no echo, and on a
match writes ``pin_hash`` via :meth:`Person.set_pin`. An unknown email or a
mismatch exits non-zero and writes nothing. The raw PIN is never echoed,
logged, or included in any output.
"""

from getpass import getpass

from django.core.management.base import BaseCommand, CommandError

from chores.models import Person


class Command(BaseCommand):
    help = "Set a person's sign-in PIN (prompts twice, no echo)."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Email of the person to set a PIN for.")

    def handle(self, *args, **options):
        email = options["email"]

        person = Person.objects.filter(email__iexact=email).first()
        if person is None:
            raise CommandError(f"No person with email {email!r}.")

        pin = getpass("PIN: ")
        confirm = getpass("PIN (again): ")
        if pin != confirm:
            raise CommandError("PINs did not match. Nothing was changed.")

        person.set_pin(pin)
        person.save(update_fields=["pin_hash", "updated_at"])

        self.stdout.write(self.style.SUCCESS(f"PIN set for {person.name}"))
