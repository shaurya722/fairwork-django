# Documents Uploaded to Vector DB & SQLite

## ✅ Successfully Uploaded Documents

All 4 Western Australian Acts have been successfully processed, chunked, and indexed:

### 1. **Carers Recognition Act 2006**
- **Document ID:** 6
- **Type:** Reference Document
- **Year:** 2006
- **Pages:** 8
- **Chunks:** 7
- **Namespace:** `reference-2006-carers-recognition-act-2006`
- **Status:** ✓ Fully indexed (7/7 chunks)
- **Description:** Western Australian legislation recognizing and supporting carers

### 2. **Disability Services Act 1993**
- **Document ID:** 3
- **Type:** Reference Document
- **Year:** 1993
- **Pages:** 52
- **Chunks:** 52
- **Namespace:** `reference-1993-disability-services-act-1993`
- **Status:** ✓ Fully indexed (52/52 chunks)
- **Description:** Western Australian legislation governing disability services

### 3. **Guardianship of Adults Act 2016**
- **Document ID:** 4
- **Type:** Reference Document
- **Year:** 2016
- **Pages:** 62
- **Chunks:** 61
- **Namespace:** `reference-2016-guardianship-of-adults-act-2016`
- **Status:** ✓ Fully indexed (61/61 chunks)
- **Description:** Western Australian legislation on guardianship and administration for adults

### 4. **Mental Health and Related Services Act 1998**
- **Document ID:** 5
- **Type:** Reference Document
- **Year:** 1998
- **Pages:** 161
- **Chunks:** 160
- **Namespace:** `reference-1998-mental-health-and-related-services-act-1`
- **Status:** ✓ Fully indexed (160/160 chunks)
- **Description:** Western Australian legislation governing mental health services

---

## 📊 Summary

- **Total Documents:** 4
- **Total Pages:** 283
- **Total Chunks:** 280
- **All chunks successfully indexed to Pinecone:** ✅

---

## 🔧 Technical Details

### Storage
- **SQLite Database:** All document metadata and chunks stored in `awards_document` and `awards_documentchunk` tables
- **Pinecone Vector DB:** All chunks embedded and indexed with isolated namespaces per document

### Document Processing
- **Chunking:** ~3600 characters per chunk with 200-character overlap
- **Embedding Model:** `nomic-embed-text` (768 dimensions)
- **Sentence Boundary Detection:** Enabled for clean chunk breaks

### Models Added
- `Document` model: Generic document storage with support for multiple types (NDIS, policy, procedure, training, reference, other)
- `DocumentChunk` model: Individual retrievable chunks with vector IDs

### Management Command
```bash
python3 manage.py upload_document <file_path> \
  --title "Document Title" \
  --type reference \
  --year "2006" \
  --description "Optional description"
```

---

## 🔍 How to Query These Documents

### Option 1: Query Specific Namespace (Current Implementation)
```python
from services.vectorstore import query
from services.embeddings import embed_text

# Query a specific Act
vector = embed_text("What are the obligations of carers?")
results = query(vector, top_k=5, namespace="reference-2006-carers-recognition-act-2006")
```

### Option 2: Multi-Namespace Search (Recommended for Future)
To enable the chatbot to search across all documents automatically, modify the RAG pipeline to:
1. Query multiple namespaces in parallel
2. Merge and re-rank results
3. Return top-k across all sources

---

## 📝 Next Steps

1. **Update RAG Pipeline:** Modify `services/rag.py` to query multiple namespaces (SCHADS award + all reference documents)
2. **Add Document Type Filter:** Allow users to specify which document types to search (e.g., "[REFERENCE] What are carer obligations?")
3. **Create Admin Interface:** Build a web UI to manage uploaded documents
4. **Add More Documents:** Upload company policies, procedures, training materials using the same command

---

## 🎯 Usage Examples

### Upload a Company Policy
```bash
python3 manage.py upload_document \
  "policies/Code_of_Conduct.pdf" \
  --title "Code of Conduct" \
  --type policy \
  --year "2024" \
  --description "Employee code of conduct and ethics policy"
```

### Upload Training Material
```bash
python3 manage.py upload_document \
  "training/NDIS_Worker_Screening.pdf" \
  --title "NDIS Worker Screening Guide" \
  --type training \
  --year "2024" \
  --description "Guide to NDIS worker screening requirements"
```

### List All Documents
```bash
python3 manage.py shell -c "from awards.models import Document; [print(f'{d.id}: {d.title} ({d.document_type})') for d in Document.objects.all()]"
```

### Delete a Document
```bash
python3 manage.py shell -c "from awards.models import Document; Document.objects.get(id=6).delete(); print('Deleted')"
```
