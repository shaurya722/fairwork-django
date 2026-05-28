# Document Upload API - Quick Reference Card

## 🚀 Upload a Document

```bash
curl -X POST http://localhost:8000/api/documents/upload/ \
  -F "file=@document.pdf" \
  -F "document_type=policy" \
  -F "title=Document Title" \
  -F "year=2024" \
  -F "version=v1.0" \
  -F "activate=true"
```

## 📋 List Documents

```bash
# All documents
curl http://localhost:8000/api/documents/

# Filter by type
curl http://localhost:8000/api/documents/?document_type=policy

# Only active
curl http://localhost:8000/api/documents/?is_active=true
```

## 🗑️ Delete Document

```bash
curl -X DELETE http://localhost:8000/api/documents/1/
```

---

## 📁 Document Types

| Type | Use For |
|------|---------|
| `ndis` | NDIS pricing documents |
| `policy` | Company policies (HR, safety, etc.) |
| `procedure` | SOPs, workflows |
| `training` | Training materials, guides |
| `reference` | Technical references, manuals |
| `other` | Anything else |

## 📄 Supported Formats

- ✅ PDF (.pdf)
- ✅ Text (.txt, .md, .markdown)
- ✅ Word (.docx)
- ✅ HTML (.html, .htm)

---

## 🔍 Query Example (Python)

```python
from services import vectorstore, embeddings

# Embed question
question = "What is the fire evacuation procedure?"
vector = embeddings.embed_text(question)

# Search specific namespace
results = vectorstore.query(
    vector,
    top_k=5,
    namespace="policy-company-safety-policy"
)

# Print results
for result in results:
    print(f"Score: {result['score']:.4f}")
    print(f"Content: {result['metadata']['content'][:200]}...")
```

---

## 📊 Check Status

```python
from awards.models import Document

# List all documents
for doc in Document.objects.all():
    print(f"{doc.title}: {doc.chunk_count} chunks, "
          f"{doc.chunks.filter(is_indexed=True).count()} indexed")
```

---

## 🎯 Common Tasks

### Upload Company Policy
```bash
curl -X POST http://localhost:8000/api/documents/upload/ \
  -F "file=@safety_policy.pdf" \
  -F "document_type=policy" \
  -F "title=Workplace Safety Policy" \
  -F "year=2024"
```

### Upload Training Material
```bash
curl -X POST http://localhost:8000/api/documents/upload/ \
  -F "file=@onboarding.pdf" \
  -F "document_type=training" \
  -F "title=New Employee Onboarding"
```

### Upload SOP
```bash
curl -X POST http://localhost:8000/api/documents/upload/ \
  -F "file=@incident_response.pdf" \
  -F "document_type=procedure" \
  -F "title=Incident Response Procedure"
```

---

## 🔧 Troubleshooting

### Check Pinecone Namespaces
```python
from services import vectorstore

stats = vectorstore.get_index().describe_index_stats()
for ns, summary in stats.namespaces.items():
    count = summary.vector_count if hasattr(summary, 'vector_count') else summary
    print(f"{ns}: {count} vectors")
```

### Re-index Failed Chunks
```python
from awards.models import Document, DocumentChunk
from services import embeddings, vectorstore
from django.utils import timezone

doc = Document.objects.get(id=1)
failed = DocumentChunk.objects.filter(document=doc, is_indexed=False)

for chunk in failed:
    vector = embeddings.embed_text(chunk.content)
    vectorstore.upsert([{
        'id': chunk.vector_id,
        'values': vector,
        'metadata': {...}
    }], namespace=doc.namespace)
    
    chunk.is_indexed = True
    chunk.indexed_at = timezone.now()
    chunk.save()
```

---

## 📞 API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/documents/upload/` | POST | Upload document |
| `/api/documents/` | GET | List documents |
| `/api/documents/<id>/` | DELETE | Delete document |

**Base URL**: `http://localhost:8000/api/`

---

## ⚙️ Configuration

### Chunk Size
- Default: 3600 characters
- Min: 500 characters
- Max: 10000 characters

```bash
curl -X POST http://localhost:8000/api/documents/upload/ \
  -F "file=@doc.pdf" \
  -F "chunk_size=2000" \
  ...
```

### Custom Namespace
```bash
curl -X POST http://localhost:8000/api/documents/upload/ \
  -F "file=@doc.pdf" \
  -F "namespace=my-custom-namespace" \
  ...
```

---

## 📚 Full Documentation

See `DOCUMENT_UPLOAD_API.md` for complete documentation.
