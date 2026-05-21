"""Import the SCHADS calculation CSV files as chatbot knowledge-base documents."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from awards import ingest
from awards.models import AwardClause
from services import knowledge


class Command(BaseCommand):
    help = (
        "Flatten the 'Award Calculation' CSV files into knowledge-base "
        "documents the chatbot can retrieve and ground answers on."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dir",
            default=str(settings.BASE_DIR),
            help="Directory holding the 'Award Calculation - *.csv' files.",
        )
        parser.add_argument(
            "--fresh",
            action="store_true",
            help="Delete existing SCHADS-CALC knowledge before importing.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without writing to the database.",
        )
        parser.add_argument(
            "--from-fixture",
            action="store_true",
            help="Load from awards/fixtures/schads_calc_knowledge.json instead of CSVs.",
        )

    def handle(self, *args, **options):
        base_dir = options["dir"]
        dry_run = options["dry_run"]
        fresh = options["fresh"]
        from_fixture = options["from_fixture"]

        # Optional: clear old knowledge first.
        if fresh and not dry_run:
            deleted = knowledge.clear_knowledge()
            self.stdout.write(
                self.style.WARNING(
                    f"Cleared {deleted} existing SCHADS-CALC chunks (--fresh)."
                )
            )

        if from_fixture:
            chunks, missing = knowledge.load_from_fixture()
            source_label = "fixture"
        else:
            chunks, missing = knowledge.build_knowledge_chunks(
                base_dir, settings.AWARD.get("CHUNK_CHARS", 3600)
            )
            source_label = "CSV"

        for name in missing:
            self.stdout.write(self.style.WARNING(f"  not found, skipped: {name}"))
        if not chunks:
            raise CommandError(
                f"No SCHADS-CALC knowledge found (source: {source_label})."
            )

        self.stdout.write(
            f"Found {len(chunks)} chunk(s) from {source_label}."
        )

        if dry_run:
            for ch in chunks:
                self.stdout.write(
                    f"  {ch['award_code']} | {ch['clause_no']:15} | "
                    f"chunk {ch['chunk_index']:2} | "
                    f"{ch['token_estimate']:4} tokens | {ch['title'][:50]}"
                )
            self.stdout.write(
                self.style.NOTICE(
                    f"Dry run complete — {len(chunks)} chunks would be stored.\n"
                    f"Next (without --dry-run): python manage.py index_award --code "
                    f"{knowledge.KNOWLEDGE_AWARD_CODE}"
                )
            )
            return

        created, updated, _ = ingest.store_clauses(
            chunks, knowledge.KNOWLEDGE_AWARD_CODE
        )
        total = AwardClause.objects.filter(
            award_code=knowledge.KNOWLEDGE_AWARD_CODE
        ).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Stored calculation knowledge base: {created} created, "
                f"{updated} updated ({total} chunks under "
                f"'{knowledge.KNOWLEDGE_AWARD_CODE}').\n"
                f"Next: python manage.py index_award --code "
                f"{knowledge.KNOWLEDGE_AWARD_CODE}"
            )
        )
