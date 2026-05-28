"""Upload and index generic documents (PDFs, DOCX, TXT, HTML) to vector DB and SQLite."""

import logging
from pathlib import Path
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from awards.models import Document, DocumentChunk
from services.document_processor import (
    chunk_document,
    get_page_count,
    make_vector_id,
    DocumentProcessingError,
)
from services.embeddings import embed_text

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Upload and index a document to vector DB and SQLite"

    def add_arguments(self, parser):
        parser.add_argument(
            'file_path',
            type=str,
            help='Path to the document file (PDF, DOCX, TXT, HTML)'
        )
        parser.add_argument(
            '--title',
            type=str,
            required=True,
            help='Document title'
        )
        parser.add_argument(
            '--type',
            type=str,
            default='reference',
            choices=['ndis', 'policy', 'procedure', 'training', 'reference', 'other'],
            help='Document type/category'
        )
        parser.add_argument(
            '--year',
            type=str,
            default='',
            help='Year or version identifier (e.g., "2024-25")'
        )
        parser.add_argument(
            '--description',
            type=str,
            default='',
            help='Optional description'
        )
        parser.add_argument(
            '--skip-index',
            action='store_true',
            help='Skip Pinecone indexing (only store in SQLite)'
        )

    def handle(self, *args, **options):
        file_path = Path(options['file_path'])
        
        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")
        
        title = options['title']
        doc_type = options['type']
        year = options['year']
        description = options['description']
        skip_index = options['skip_index']
        
        self.stdout.write(f"Processing: {file_path.name}")
        self.stdout.write(f"Title: {title}")
        self.stdout.write(f"Type: {doc_type}")
        
        try:
            # 1. Check if document already exists
            existing = Document.objects.filter(
                title=title,
                document_type=doc_type
            ).first()
            
            if existing:
                self.stdout.write(
                    self.style.WARNING(
                        f"Document '{title}' already exists (ID: {existing.id}). "
                        f"Delete it first or use a different title."
                    )
                )
                return
            
            # 2. Process the document
            self.stdout.write("Chunking document...")
            chunks_data = chunk_document(
                file_path,
                chunk_chars=3600,
                document_type=doc_type,
                title=title
            )
            
            page_count = get_page_count(file_path)
            
            self.stdout.write(
                f"✓ Extracted {len(chunks_data)} chunks from {page_count} pages"
            )
            
            # 3. Create Document record
            with transaction.atomic():
                doc = Document.objects.create(
                    document_type=doc_type,
                    title=title,
                    year=year,
                    description=description,
                    source_file=file_path.name,
                    page_count=page_count,
                    chunk_count=len(chunks_data),
                    is_active=True,
                )
                
                # Generate namespace
                doc.namespace = doc.generate_namespace()
                doc.save(update_fields=['namespace'])
                
                self.stdout.write(
                    f"✓ Created document (ID: {doc.id}, namespace: {doc.namespace})"
                )
                
                # 4. Create chunks in SQLite
                chunk_objects = []
                for chunk_data in chunks_data:
                    chunk_objects.append(
                        DocumentChunk(
                            document=doc,
                            chunk_index=chunk_data['chunk_index'],
                            content=chunk_data['content'],
                            page_start=chunk_data['page_start'],
                            page_end=chunk_data['page_end'],
                            section=chunk_data['section'],
                            token_estimate=chunk_data['token_estimate'],
                            vector_id=make_vector_id(
                                doc.id,
                                chunk_data['chunk_index'],
                                doc.namespace
                            ),
                            is_indexed=False,
                        )
                    )
                
                DocumentChunk.objects.bulk_create(chunk_objects)
                self.stdout.write(f"✓ Saved {len(chunk_objects)} chunks to SQLite")
            
            # 5. Index to Pinecone
            if not skip_index:
                self.stdout.write("Indexing to Pinecone...")
                indexed_count = self._index_to_pinecone(doc)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Indexed {indexed_count} chunks to Pinecone namespace '{doc.namespace}'"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING("⚠ Skipped Pinecone indexing (--skip-index)")
                )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✅ Document uploaded successfully!\n"
                    f"   ID: {doc.id}\n"
                    f"   Title: {doc.title}\n"
                    f"   Type: {doc.document_type}\n"
                    f"   Namespace: {doc.namespace}\n"
                    f"   Chunks: {doc.chunk_count}"
                )
            )
            
        except DocumentProcessingError as exc:
            raise CommandError(f"Document processing failed: {exc}")
        except Exception as exc:
            logger.exception("Unexpected error during document upload")
            raise CommandError(f"Upload failed: {exc}")
    
    def _index_to_pinecone(self, doc: Document) -> int:
        """Index all chunks of a document to Pinecone."""
        from services.vectorstore import get_index
        
        index = get_index()
        chunks = doc.chunks.filter(is_indexed=False)
        
        if not chunks.exists():
            return 0
        
        vectors = []
        chunk_ids = []
        
        for chunk in chunks:
            # Generate embedding
            embedding = embed_text(chunk.content)
            
            # Prepare vector with metadata
            vectors.append({
                'id': chunk.vector_id,
                'values': embedding,
                'metadata': {
                    'document_id': doc.id,
                    'document_type': doc.document_type,
                    'title': doc.title,
                    'chunk_index': chunk.chunk_index,
                    'section': chunk.section,
                    'page_start': chunk.page_start,
                    'page_end': chunk.page_end,
                    'content': chunk.content,  # Full chunk for grounding in RAG answers
                }
            })
            chunk_ids.append(chunk.id)
            
            # Batch upsert every 100 vectors
            if len(vectors) >= 100:
                index.upsert(vectors=vectors, namespace=doc.namespace)
                vectors = []
        
        # Upsert remaining vectors
        if vectors:
            index.upsert(vectors=vectors, namespace=doc.namespace)
        
        # Mark chunks as indexed
        DocumentChunk.objects.filter(id__in=chunk_ids).update(
            is_indexed=True,
            indexed_at=datetime.now(timezone.utc)
        )
        
        return len(chunk_ids)