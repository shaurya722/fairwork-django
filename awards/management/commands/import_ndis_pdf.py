"""Ingest an NDIS Pricing Arrangements & Price Limits PDF.

Workflow:

1. Parse the PDF into chunks (``services.ndis_pdf.chunk_pdf``).
2. Upsert ``NDISDocument`` + ``NDISChunk`` rows in SQLite.
3. Embed each chunk via Ollama and push the vectors to the per-year Pinecone
   namespace (e.g. ``ndis-2024-25``).

Example:

    python manage.py import_ndis_pdf \
        "NDIS Pricing Arrangements and Price Limits 2024-25 v1.3 (18).pdf" \
        --year 2024-25 --doc-version v1.3 --activate

``--activate`` marks the new document as the active one
for its year and
deactivates older versions for the same year.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from awards.models import NDISChunk, NDISDocument
from services import embeddings, ndis_pdf, vectorstore


class Command(BaseCommand):
    help = (
        "Import an NDIS Pricing Arrangements PDF: parse, store in SQLite, "
        "and index into a per-year Pinecone namespace."
    )

    def add_arguments(self, parser):
        parser.add_argument("pdf_path", help="Path to the NDIS pricing PDF.")
        parser.add_argument(
            "--year",
            required=True,
            help="Fiscal year label, e.g. '2024-25'.",
        )
        # ``--version`` collides with Django's built-in version flag, so the
        # CLI flag is ``--doc-version``. The handler reads ``opts["doc_version"]``.
        parser.add_argument(
            "--doc-version",
            dest="doc_version",
            default="",
            help="Document version, e.g. 'v1.3'.",
        )
        parser.add_argument(
            "--title",
            default="NDIS Pricing Arrangements and Price Limits",
            help="Human-readable title stored on the NDISDocument row.",
        )
        parser.add_argument(
            "--source-url",
            default="",
            help="Optional canonical URL the PDF was downloaded from.",
        )
        parser.add_argument(
            "--chunk-chars",
            type=int,
            default=settings.AWARD["CHUNK_CHARS"],
            help="Approximate character size per chunk (default matches award scraper).",
        )
        parser.add_argument(
            "--activate",
            action="store_true",
            help=(
                "Mark this document active and deactivate other versions "
                "for the same year."
            ),
        )
        parser.add_argument(
            "--skip-embedding",
            action="store_true",
            help="Only parse and store in SQLite; skip Pinecone embedding.",
        )
        parser.add_argument(
            "--recreate",
            action="store_true",
            help=(
                "Delete every existing vector for this year's Pinecone "
                "namespace before upserting."
            ),
        )

    @transaction.atomic
    def _store_document(self, *, pdf_path, year, version, title, source_url, chunk_chars, activate):
        chunks = ndis_pdf.chunk_pdf(pdf_path, chunk_chars=chunk_chars)
        pages = ndis_pdf.page_count(pdf_path)

        doc, _ = NDISDocument.objects.update_or_create(
            year=year,
            version=version,
            defaults={
                "title": title,
                "source_file": str(Path(pdf_path).name),
                "source_url": source_url,
                "page_count": pages,
                "chunk_count": len(chunks),
                "is_active": True if activate else True,
            },
        )

        if activate:
            NDISDocument.objects.filter(year=year).exclude(pk=doc.pk).update(
                is_active=False
            )

        # Reset existing chunks so vector ids stay aligned with chunk_index.
        NDISChunk.objects.filter(document=doc).delete()

        chunk_rows = []
        for chunk in chunks:
            vector_id = ndis_pdf.make_vector_id(year, version or "v0", chunk["chunk_index"])
            chunk_rows.append(
                NDISChunk(
                    document=doc,
                    section=chunk["section"],
                    page_start=chunk["page_start"],
                    page_end=chunk["page_end"],
                    chunk_index=chunk["chunk_index"],
                    content=chunk["content"],
                    token_estimate=chunk["token_estimate"],
                    vector_id=vector_id,
                    is_indexed=False,
                )
            )
        NDISChunk.objects.bulk_create(chunk_rows)
        return doc, chunk_rows

    def handle(self, *args, **opts):
        pdf_path = opts["pdf_path"]
        year = opts["year"].strip()
        version = (opts.get("doc_version") or "").strip()
        title = opts["title"]
        source_url = opts["source_url"]
        chunk_chars = opts["chunk_chars"]
        activate = opts["activate"]

        self.stdout.write(f"Parsing {pdf_path} ...")
        try:
            doc, chunks = self._store_document(
                pdf_path=pdf_path,
                year=year,
                version=version,
                title=title,
                source_url=source_url,
                chunk_chars=chunk_chars,
                activate=activate,
            )
        except ndis_pdf.NDISPdfError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            f"Stored NDISDocument id={doc.id} year={doc.year} version={doc.version!r} "
            f"pages={doc.page_count} chunks={len(chunks)}"
        )

        if opts["skip_embedding"]:
            self.stdout.write(
                self.style.WARNING(
                    "Skipped embedding. Run without --skip-embedding to push "
                    "vectors to Pinecone."
                )
            )
            return

        self._embed_and_upsert(doc, chunks, recreate=opts["recreate"])

    def _embed_and_upsert(self, doc: NDISDocument, chunks, *, recreate: bool):
        embed_model = settings.OLLAMA["EMBED_MODEL"]
        self.stdout.write(
            f"Embedding {len(chunks)} chunks with '{embed_model}' for namespace "
            f"'{doc.pinecone_namespace}' ..."
        )

        try:
            dimension = embeddings.embedding_dimension()
        except embeddings.EmbeddingError as exc:
            raise CommandError(str(exc)) from exc

        configured_dim = settings.PINECONE["DIMENSION"]
        if dimension != configured_dim:
            self.stdout.write(
                self.style.WARNING(
                    f"Probed dimension ({dimension}) != PINECONE_DIMENSION "
                    f"({configured_dim}). Set PINECONE_DIMENSION={dimension}."
                )
            )

        try:
            vectorstore.ensure_index(dimension)
            if recreate:
                vectorstore.delete_all(namespace=doc.pinecone_namespace)
                NDISChunk.objects.filter(document=doc).update(
                    is_indexed=False, indexed_at=None
                )
                self.stdout.write(
                    f"Cleared namespace '{doc.pinecone_namespace}'."
                )

            vectors = []
            for position, chunk in enumerate(chunks, start=1):
                vector = embeddings.embed_text(chunk.content)
                vectors.append(
                    {
                        "id": chunk.vector_id,
                        "values": vector,
                        "metadata": {
                            "kind": "ndis",
                            "year": doc.year,
                            "version": doc.version,
                            "title": doc.title,
                            "section": chunk.section,
                            "page_start": chunk.page_start,
                            "page_end": chunk.page_end,
                            "chunk_index": chunk.chunk_index,
                            "content": chunk.content,
                            "source_file": doc.source_file,
                            "source_url": doc.source_url,
                        },
                    }
                )
                if position % 10 == 0 or position == len(chunks):
                    self.stdout.write(f"  embedded {position}/{len(chunks)}")

            self.stdout.write(
                f"Upserting {len(vectors)} vectors to namespace "
                f"'{doc.pinecone_namespace}' ..."
            )
            vectorstore.upsert(vectors, namespace=doc.pinecone_namespace)
        except vectorstore.VectorStoreError as exc:
            raise CommandError(str(exc)) from exc

        now = timezone.now()
        for chunk in chunks:
            chunk.is_indexed = True
            chunk.indexed_at = now
        NDISChunk.objects.bulk_update(chunks, ["is_indexed", "indexed_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Indexed {len(chunks)} NDIS chunks into Pinecone index "
                f"'{settings.PINECONE['INDEX_NAME']}' namespace "
                f"'{doc.pinecone_namespace}'.\n"
                f"Query at POST /api/ndis-chat/"
            )
        )
