"""Create a read-only API token and print it once.

    docker compose exec backend python manage.py create_api_token --name claude-prospection

The token is only stored as a hash, so it cannot be shown again: revoke it in
the admin and create another if it is lost. It is accepted on the routes that
declare `api_token_auth` (see prospect/security.py) and nowhere else.
"""

from django.core.management.base import BaseCommand, CommandError

from emails.models import ApiToken
from emails.services.api_tokens import create_token


class Command(BaseCommand):
    help = "Create a read-only API token and print it once."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="Who or what the token is for")

    def handle(self, *args, **options):
        name = options["name"].strip()
        if not name:
            raise CommandError("--name must not be empty")
        if ApiToken.objects.filter(name=name).exists():
            raise CommandError(f"A token named {name!r} already exists; revoke it in the admin first.")
        token = create_token(name)
        self.stderr.write(f"Token {name!r} created. It is shown once; store it now.")
        self.stdout.write(token)
