"""Scrape a Fair Work award and store its clause chunks in SQLite."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from awards import ingest
from awards.models import AwardClause
from services import scraper, wages


class Command(BaseCommand):
    help = "Scrape a Fair Work award webpage and store clause chunks in SQLite."

    def add_arguments(self, parser):
        parser.add_argument("--url", default=settings.AWARD["URL"], help="Award page URL.")
        parser.add_argument("--code", default=settings.AWARD["CODE"], help="Award code.")
        parser.add_argument(
            "--fresh",
            action="store_true",
            help="Delete existing clauses for this award before scraping.",
        )

    def handle(self, *args, **options):
        url = options["url"]
        code = options["code"]

        self.stdout.write(f"Scraping award {code} from {url} ...")
        try:
            chunks = scraper.scrape_award(url, code, settings.AWARD["CHUNK_CHARS"])
        except scraper.ScrapeError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Parsed {len(chunks)} clause chunks.")

        created, updated, removed = ingest.store_clauses(
            chunks, code, fresh=options["fresh"]
        )
        if removed:
            self.stdout.write(f"Removed {removed} existing rows for {code}.")

        # Augment the weekly-wage clauses (15, 16, 17) with an hourly rate.
        hourly = wages.apply_hourly_rates(award_code=code)
        if hourly:
            self.stdout.write(f"Added hourly rates to {hourly} wage clause chunk(s).")

        total = AwardClause.objects.filter(award_code=code).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Stored in SQLite: {created} created, {updated} updated "
                f"({total} total for {code}).\n"
                f"Next: python manage.py index_award"
            )
        )
