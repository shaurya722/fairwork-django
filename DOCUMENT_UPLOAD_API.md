# Document Upload & Management API

## Overview

The Document Upload API allows you to upload and index different types of documents (PDF, TXT, DOCX, MD, HTML) into the vector database. Each document is:

1. **Parsed and chunked** into manageable pieces
2. **Stored in SQLite** for persistence
3. **Embedded using Ollama** (nomic-embed-text)
4. **Indexed into Pinecone** in its own namespace for isolated retrieval

---

## Supported Document Types

| Type | Description | Use Case |
|------|-------------|----------|
| `ndis` | NDIS Pricing Document | NDIS pricing arrangements, price limits |
| `policy` | Company Policy | HR policies, safety policies, compliance docs |
| `procedure` | Standard Operating Procedure | SOPs, workflows, process documentation |
| `training` | Training Material | Training guides, onboarding materials |
| `reference` | Reference Document | Technical references, manuals |
| `other` | Other Document | Any other document type |

## Supported File Formats

- **PDF** (.pdf) - Extracted using PyPDF2
- **Text** (.txt, .md, .markdown) - Plain text files
- **Word** (.docx) - Requires python-docx (optional)
- **HTML** (.html, .htm) - Basic HTML parsing

---

## API Endpoints

### 1. Upload Document

**POST** `/api/documents/upload/`

Upload and index a document into the vector database.

#### Request

**Content-Type**: `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | ✅ Yes | Document file to upload |
| `document_type` | String | ✅ Yes | Type: `ndis`, `policy`, `procedure`, `training`, `reference`, `other` |
| `title` | String | ✅ Yes | Human-readable document title |
| `year` | String | ❌ No | Fiscal year (e.g., "2024-25") |
| `version` | String | ❌ No | Document version (e.g., "v1.3") |
| `source_url` | URL | ❌ No | Original URL where document was obtained |
| `description` | String | ❌ No | Optional description or notes |
| `chunk_size` | Integer | ❌ No | Chunk size in characters (default: 3600, min: 500, max: 10000) |
| `activate` | Boolean | ❌ No | Mark as active for searches (default: true) |
| `namespace` | String | ❌ No | Custom Pinecone namespace (auto-generated if not provided) |

#### Response (201 Created)

```json
{
  "success": true,
  "document_id": 1,
  "title": "Company Safety Policy",
  "document_type": "policy",
  "namespace": "policy-company-safety-policy",
  "chunks_created": 45,
  "chunks_indexed": 45,
  "page_count": 12,
  "message": "Document uploaded and indexed successfully"
}
```

#### Error Response (400 Bad Request)

```json
{
  "success": false,
  "error": "Unsupported file type: .xlsx. Supported: .pdf, .txt, .md, .docx, .html"
}
```

#### cURL Example

```bash
curl -X POST http://localhost:8000/api/documents/upload/ \
  -F "file=@/path/to/safety_policy.pdf" \
  -F "document_type=policy" \
  -F "title=Company Safety Policy" \
  -F "year=2024" \
  -F "version=v2.1" \
  -F "description=Updated safety procedures for 2024" \
  -F "activate=true"
```

#### Python Example

```python
import requests

url = "http://localhost:8000/api/documents/upload/"

with open("safety_policy.pdf", "rb") as f:
    files = {"file": f}
    data = {
        "document_type": "policy",
        "title": "Company Safety Policy",
        "year": "2024",
        "version": "v2.1",
        "description": "Updated safety procedures",
        "activate": "true"
    }
    
    response = requests.post(url, files=files, data=data)
    print(response.json())
```

---

### 2. List Documents

**GET** `/api/documents/`

Retrieve a list of all uploaded documents with their indexing status.

#### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `document_type` | String | Filter by type (ndis, policy, procedure, etc.) |
| `is_active` | Boolean | Filter by active status (true/false) |

#### Response (200 OK)

```json
{
  "count": 3,
  "documents": [
    {
      "id": 1,
      "document_type": "policy",
      "title": "Company Safety Policy",
      "year": "2024",
      "version": "v2.1",
      "source_file": "safety_policy.pdf",
      "source_url": "https://example.com/policies/safety.pdf",
      "is_active": true,
      "chunk_count": 45,
      "indexed_count": 45,
      "created_at": "2024-05-26T10:00:00Z",
      "namespace": "policy-company-safety-policy"
    },
    {
      "id": 2,
      "document_type": "training",
      "title": "New Employee Onboarding Guide",
      "year": "2024",
      "version": "v1.0",
      "source_file": "onboarding.pdf",
      "source_url": "",
      "is_active": true,
      "chunk_count": 32,
      "indexed_count": 32,
      "created_at": "2024-05-25T14:30:00Z",
      "namespace": "training-new-employee-onboarding-guide"
    },
    {
      "id": 3,
      "document_type": "ndis",
      "title": "NDIS Pricing Arrangements 2024-25",
      "year": "2024-25",
      "version": "v1.3",
      "source_file": "NDIS_Pricing_2024-25.pdf",
      "source_url": "https://ndis.gov.au/pricing",
      "is_active": true,
      "chunk_count": 94,
      "indexed_count": 94,
      "created_at": "2024-05-26T11:00:00Z",
      "namespace": "ndis-2024-25-ndis-pricing-arrangements-2024-25"
    }
  ]
}
```

#### cURL Example

```bash
# List all documents
curl http://localhost:8000/api/documents/

# List only policy documents
curl http://localhost:8000/api/documents/?document_type=policy

# List only active documents
curl http://localhost:8000/api/documents/?is_active=true
```

---

### 3. Delete Document

**DELETE** `/api/documents/<document_id>/`

Delete a document and all its vectors from both the database and Pinecone.

#### Response (200 OK)

```json
{
  "success": true,
  "message": "Document deleted successfully",
  "chunks_deleted": 45,
  "vectors_deleted": true
}
```

#### Error Response (404 Not Found)

```json
{
  "success": false,
  "error": "Document not found"
}
```

#### cURL Example

```bash
curl -X DELETE http://localhost:8000/api/documents/1/
```

---

## Document Processing Pipeline

### 1. File Upload
```
User uploads file → Saved to temp location
```

### 2. Document Parsing
```
PDF → PyPDF2 extracts text per page
TXT/MD → Read as single page
DOCX → Extract paragraphs, group into logical pages
HTML → Strip tags, extract text
```

### 3. Chunking
```
Text split into ~3600 char chunks
Overlap of 200 chars between chunks
Smart sentence boundary detection
Section headers detected and preserved
```

### 4. Database Storage
```
Document record created in SQLite
Chunks stored with metadata:
  - chunk_index (0, 1, 2, ...)
  - content (full text)
  - section (detected header)
  - page_start, page_end
  - token_estimate
  - vector_id (for Pinecone linking)
```

### 5. Embedding & Indexing
```
Each chunk embedded via Ollama (nomic-embed-text)
768-dimensional vectors created
Vectors upserted to Pinecone namespace
Chunks marked as indexed in DB
```

### 6. Namespace Organization
```
Each document gets its own namespace:
  - policy-company-safety-policy
  - training-new-employee-onboarding-guide
  - ndis-2024-25-ndis-pricing-arrangements-2024-25

This allows isolated retrieval per document type
```

---

## Namespace Naming Convention

Namespaces are auto-generated from:
```
{document_type}-{year}-{title_slug}
```

Examples:
- `policy-company-safety-policy`
- `policy-2024-company-safety-policy` (with year)
- `training-new-employee-onboarding-guide`
- `ndis-2024-25-ndis-pricing-arrangements-2024-25`

You can also provide a custom namespace via the `namespace` parameter.

---

## Vector Metadata

Each vector in Pinecone includes:

```json
{
  "id": "policy-company-safety-policy-doc1-0",
  "values": [0.123, -0.456, ...],  // 768-dim embedding
  "metadata": {
    "kind": "policy",
    "document_id": 1,
    "title": "Company Safety Policy",
    "year": "2024",
    "version": "v2.1",
    "section": "Emergency Procedures",
    "page_start": 5,
    "page_end": 5,
    "chunk_index": 0,
    "content": "[POLICY] Company Safety Policy\n\nEmergency Procedures...",
    "source_file": "safety_policy.pdf",
    "source_url": "https://example.com/policies/safety.pdf"
  }
}
```

---

## Integration with Chatbot

### Querying Specific Document Types

The chatbot can be extended to search specific namespaces:

```python
# Search only policy documents
from services import vectorstore, embeddings

question = "What is the fire evacuation procedure?"
vector = embeddings.embed_text(question)
results = vectorstore.query(
    vector, 
    top_k=5, 
    namespace="policy-company-safety-policy"
)
```

### Multi-Namespace Search

Search across multiple document types:

```python
# Search policies + training materials
namespaces = [
    "policy-company-safety-policy",
    "training-new-employee-onboarding-guide"
]

all_results = []
for ns in namespaces:
    results = vectorstore.query(vector, top_k=3, namespace=ns)
    all_results.extend(results)

# Sort by score and take top 5
all_results.sort(key=lambda x: x['score'], reverse=True)
top_results = all_results[:5]
```

---

## Example Use Cases

### Use Case 1: Company Policy Library

Upload all company policies:

```bash
# HR Policy
curl -X POST http://localhost:8000/api/documents/upload/ \
  -F "file=@hr_policy.pdf" \
  -F "document_type=policy" \
  -F "title=HR Policy Manual" \
  -F "year=2024"

# Safety Policy
curl -X POST http://localhost:8000/api/documents/upload/ \
  -F "file=@safety_policy.pdf" \
  -F "document_type=policy" \
  -F "title=Workplace Safety Policy" \
  -F "year=2024"

# IT Security Policy
curl -X POST http://localhost:8000/api/documents/upload/ \
  -F "file=@it_security.pdf" \
  -F "document_type=policy" \
  -F "title=IT Security Policy" \
  -F "year=2024"
```

Now the chatbot can answer questions like:
- "What is the sick leave policy?"
- "How do I report a workplace injury?"
- "What are the password requirements?"

### Use Case 2: Training Materials

Upload training guides:

```bash
curl -X POST http://localhost:8000/api/documents/upload/ \
  -F "file=@onboarding.pdf" \
  -F "document_type=training" \
  -F "title=New Employee Onboarding" \
  -F "description=Complete onboarding guide for new hires"
```

### Use Case 3: SOPs (Standard Operating Procedures)

```bash
curl -X POST http://localhost:8000/api/documents/upload/ \
  -F "file=@incident_response.pdf" \
  -F "document_type=procedure" \
  -F "title=Incident Response Procedure" \
  -F "version=v3.2"
```

---

## Monitoring & Troubleshooting

### Check Document Status

```bash
# List all documents
curl http://localhost:8000/api/documents/

# Check if all chunks are indexed
# Look for: "chunk_count": 45, "indexed_count": 45
```

### Verify Pinecone Namespace

```python
from services import vectorstore

stats = vectorstore.get_index().describe_index_stats()
print(stats.namespaces)

# Output:
# {
#   'ma000100': NamespaceSummary(vector_count=91),
#   'ndis-2024-25': NamespaceSummary(vector_count=94),
#   'policy-company-safety-policy': NamespaceSummary(vector_count=45)
# }
```

### Re-index Failed Chunks

If some chunks failed to index, you can manually re-index:

```python
from awards.models import Document, DocumentChunk
from services import embeddings, vectorstore
from django.utils import timezone

doc = Document.objects.get(id=1)
failed_chunks = DocumentChunk.objects.filter(document=doc, is_indexed=False)

for chunk in failed_chunks:
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

## Best Practices

### 1. Document Naming
- Use clear, descriptive titles
- Include year/version for versioned documents
- Be consistent with naming conventions

### 2. Chunk Size
- **Default (3600 chars)**: Good for most documents
- **Smaller (1500-2000)**: Better for Q&A style docs
- **Larger (5000-8000)**: Better for narrative documents

### 3. Activation Strategy
- Only activate the latest version of each document type
- Deactivate old versions to avoid confusion
- The API auto-deactivates other docs of the same type when `activate=true`

### 4. Namespace Management
- Use descriptive namespaces
- Group related documents in similar namespaces
- Consider year-based namespaces for versioned docs

### 5. File Preparation
- Ensure PDFs are text-based (not scanned images)
- Remove unnecessary formatting from text files
- Clean up HTML before uploading

---

## Limitations

1. **Scanned PDFs**: Image-only PDFs won't work (no OCR support yet)
2. **Large Files**: Very large files (>100MB) may timeout
3. **Complex Formatting**: Tables, charts, and complex layouts may not parse well
4. **Language**: Currently optimized for English text

---

## Future Enhancements

- [ ] OCR support for scanned PDFs
- [ ] Table extraction and preservation
- [ ] Image description via vision models
- [ ] Batch upload (multiple files at once)
- [ ] Document versioning and diff tracking
- [ ] Custom chunking strategies per document type
- [ ] Automatic document categorization
- [ ] Full-text search alongside vector search

---

## API Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/documents/upload/` | POST | Upload and index a document |
| `/api/documents/` | GET | List all documents |
| `/api/documents/<id>/` | DELETE | Delete a document |

**Base URL**: `http://localhost:8000/api/`

**Authentication**: None (add authentication in production!)

**Rate Limiting**: None (add rate limiting in production!)
