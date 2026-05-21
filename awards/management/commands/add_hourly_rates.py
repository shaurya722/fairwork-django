"""Add hourly wage rates (weekly wage / 38) to the stored weekly-wage clauses."""

from django.conf import settings
from django.core.management.base import BaseCommand

from services import wages


class Command(BaseCommand):
    help = (
        "Augment the minimum weekly wage clauses (15, 16, 17) with an hourly "
        "rate column — the weekly wage divided by the 38-hour standard week."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--code", default=settings.AWARD["CODE"], help="Award code."
        )

    def handle(self, *args, **options):
        code = options["code"]
        changed = wages.apply_hourly_rates(award_code=code)

        if not changed:
            self.stdout.write(
                "No clauses changed — hourly rates are already present "
                "(or clauses 15/16/17 have not been scraped yet)."
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Added hourly rates to {changed} wage clause chunk(s) for {code}.\n"
                f"Next: python manage.py index_award  (re-embeds the updated clauses)"
            )
        )
