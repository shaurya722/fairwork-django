"""Embed scraped award clauses and upsert them into Pinecone."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from awards.models import AwardClause
from services import embeddings, vectorstore


class Command(BaseCommand):
    help = "Embed award clauses (Ollama) and upsert the vectors into Pinecone."

    def add_arguments(self, parser):
        parser.add_argument("--code", default=settings.AWARD["CODE"], help="Award code.")
        parser.add_argument(
            "--all",
            action="store_true",
            help="Re-index every clause, not only the un-indexed ones.",
        )
        parser.add_argument(
            "--recreate",
            action="store_true",
            help="Delete all vectors in the Pinecone namespace first.",
        )

    def handle(self, *args, **options):
        code = options["code"]

        queryset = AwardClause.objects.filter(award_code=code)
        if not (options["all"] or options["recreate"]):
            queryset = queryset.filter(is_indexed=False)
        clauses = list(queryset)

        if not clauses:
            self.stdout.write(
                "Nothing to index. Run 'scrape_award' first, or pass --all to re-index."
            )
            return

        embed_model = settings.OLLAMA["EMBED_MODEL"]
        self.stdout.write(f"Embedding {len(clauses)} chunks with '{embed_model}' ...")
        try:
            dimension = embeddings.embedding_dimension()
        except embeddings.EmbeddingError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Embedding dimension: {dimension}")

        configured_dim = settings.PINECONE["DIMENSION"]
        if dimension != configured_dim:
            self.stdout.write(
                self.style.WARNING(
                    f"Probed dimension ({dimension}) != PINECONE_DIMENSION ({configured_dim}). "
                    f"Set PINECONE_DIMENSION={dimension} or the index query will fail."
                )
            )

        try:
            vectorstore.ensure_index(dimension)
            if options["recreate"]:
                vectorstore.delete_all()
                AwardClause.objects.filter(award_code=code).update(
                    is_indexed=False, indexed_at=None
                )
                self.stdout.write("Cleared existing vectors in the namespace.")

            vectors = []
            for position, clause in enumerate(clauses, start=1):
                vector = embeddings.embed_text(clause.content)
                vectors.append(
                    {
                        "id": clause.vector_id,
                        "values": vector,
                        "metadata": {
                            "award_code": clause.award_code,
                            "clause_no": clause.clause_no,
                            "title": clause.title,
                            "part": clause.part,
                            "chunk_index": clause.chunk_index,
                            "content": clause.content,
                            "source_url": clause.source_url,
                        },
                    }
                )
                if position % 10 == 0 or position == len(clauses):
                    self.stdout.write(f"  embedded {position}/{len(clauses)}")

            self.stdout.write(f"Upserting {len(vectors)} vectors into Pinecone ...")
            vectorstore.upsert(vectors)
        except vectorstore.VectorStoreError as exc:
            raise CommandError(str(exc)) from exc

        now = timezone.now()
        for clause in clauses:
            clause.is_indexed = True
            clause.indexed_at = now
        AwardClause.objects.bulk_update(clauses, ["is_indexed", "indexed_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Indexed {len(vectors)} chunks into Pinecone index "
                f"'{settings.PINECONE['INDEX_NAME']}' (namespace "
                f"'{settings.PINECONE['NAMESPACE']}').\n"
                f"Next: start the server and POST to /api/chat/"
            )
        )
