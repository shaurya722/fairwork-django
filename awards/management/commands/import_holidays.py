"""Import public holidays from a CSV export into the database."""

from django.core.management.base import BaseCommand, CommandError

from services import holidays


class Command(BaseCommand):
    help = (
        "Import public holidays from a CSV export. The dates are applied "
        "automatically by the chat pay calculator."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", required=True, help="Path to the public-holidays CSV export."
        )

    def handle(self, *args, **options):
        path = options["file"]
        try:
            stats = holidays.import_csv(path)
        except FileNotFoundError as exc:
            raise CommandError(f"CSV file not found: {path}") from exc
        except OSError as exc:
            raise CommandError(f"Could not read {path}: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported public holidays from {path}:\n"
                f"  created          : {stats['created']}\n"
                f"  updated          : {stats['updated']}\n"
                f"  skipped (junk)   : {stats['skipped_junk']}\n"
                f"  skipped (deleted): {stats['skipped_deleted']}\n"
                f"  errors           : {stats['errors']}"
            )
        )
