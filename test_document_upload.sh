#!/bin/bash
# Test script for Document Upload API

BASE_URL="http://localhost:8000/api"

echo "=== Document Upload API Test Suite ==="
echo

# Test 1: Create a sample text document
echo "Creating sample document..."
cat > /tmp/test_policy.txt << 'EOF'
COMPANY SAFETY POLICY
Version 2.1 - 2024

1. EMERGENCY PROCEDURES

In case of fire:
- Activate the nearest fire alarm
- Evacuate the building immediately
- Assemble at the designated meeting point
- Do not use elevators
- Wait for further instructions from fire wardens

2. WORKPLACE SAFETY

All employees must:
- Wear appropriate PPE when required
- Report hazards immediately to supervisors
- Follow all safety signage and instructions
- Participate in safety training programs
- Keep work areas clean and organized

3. INCIDENT REPORTING

All workplace incidents must be reported within 24 hours using:
- Online incident report form
- Email to safety@company.com
- Phone: 1-800-SAFETY-1

4. FIRST AID

First aid kits are located:
- Reception desk
- Kitchen area
- Warehouse entrance
- Each floor near elevators

Trained first aiders are identified by green badges.
EOF

echo "Sample document created at /tmp/test_policy.txt"
echo

# Test 2: Upload the document
echo "Test 1: Upload Policy Document"
echo "================================"
curl -X POST "${BASE_URL}/documents/upload/" \
  -F "file=@/tmp/test_policy.txt" \
  -F "document_type=policy" \
  -F "title=Company Safety Policy" \
  -F "year=2024" \
  -F "version=v2.1" \
  -F "description=Updated safety procedures for 2024" \
  -F "activate=true"
echo
echo

# Test 3: List all documents
echo "Test 2: List All Documents"
echo "=========================="
curl "${BASE_URL}/documents/"
echo
echo

# Test 4: List only policy documents
echo "Test 3: List Policy Documents Only"
echo "==================================="
curl "${BASE_URL}/documents/?document_type=policy"
echo
echo

# Test 5: List active documents
echo "Test 4: List Active Documents"
echo "=============================="
curl "${BASE_URL}/documents/?is_active=true"
echo
echo

# Test 6: Check Pinecone namespaces
echo "Test 5: Verify Pinecone Indexing"
echo "================================="
cd /home/ubuntu/Desktop/New_____Folder/Symcare/Symcare-chatbot/fairwork-django
source .venv/bin/activate
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from services import vectorstore

stats = vectorstore.get_index().describe_index_stats()
print('Pinecone Index Stats:')
print(f'  Total vectors: {stats.total_vector_count}')
print(f'  Dimension: {stats.dimension}')
print()
print('Namespaces:')
for ns, summary in stats.namespaces.items():
    count = summary.vector_count if hasattr(summary, 'vector_count') else summary
    print(f'  - {ns}: {count} vectors')
"
echo

# Test 7: Query the uploaded document
echo "Test 6: Query Uploaded Document"
echo "================================"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from awards.models import Document
from services import embeddings, vectorstore

# Get the uploaded document
doc = Document.objects.filter(document_type='policy').first()
if doc:
    print(f'Document: {doc.title}')
    print(f'Namespace: {doc.namespace}')
    print(f'Chunks: {doc.chunk_count}')
    print()
    
    # Test query
    question = 'What should I do in case of fire?'
    print(f'Question: {question}')
    print()
    
    vector = embeddings.embed_text(question)
    results = vectorstore.query(vector, top_k=3, namespace=doc.namespace)
    
    print(f'Found {len(results)} relevant chunks:')
    for i, result in enumerate(results, 1):
        print(f'  {i}. Score: {result[\"score\"]:.4f}')
        print(f'     Section: {result[\"metadata\"].get(\"section\", \"N/A\")}')
        print(f'     Preview: {result[\"metadata\"].get(\"content\", \"\")[:100]}...')
        print()
else:
    print('No policy documents found')
"
echo

echo "=== Test Suite Complete ==="
echo
echo "To delete the test document:"
echo "  curl -X DELETE ${BASE_URL}/documents/1/"
echo
echo "To clean up:"
echo "  rm /tmp/test_policy.txt"
