#!/bin/bash
# Upload the 4 WA Acts to vector DB and SQLite

set -e

echo "Uploading 4 Western Australian Acts..."
echo "========================================"
echo ""

python3 manage.py upload_document \
  "Docs/CARERS RECOGNITION ACT 2006.pdf" \
  --title "Carers Recognition Act 2006" \
  --type reference \
  --year "2006" \
  --description "Western Australian legislation recognizing and supporting carers"

echo ""
echo "---"
echo ""

python3 manage.py upload_document \
  "Docs/DISABILITY SERVICES ACT 1993.pdf" \
  --title "Disability Services Act 1993" \
  --type reference \
  --year "1993" \
  --description "Western Australian legislation governing disability services"

echo ""
echo "---"
echo ""

python3 manage.py upload_document \
  "Docs/GUARDIANSHIP OF ADULTS ACT 2016.pdf" \
  --title "Guardianship of Adults Act 2016" \
  --type reference \
  --year "2016" \
  --description "Western Australian legislation on guardianship and administration for adults"

echo ""
echo "---"
echo ""

python3 manage.py upload_document \
  "Docs/MENTAL HEALTH AND RELATED SERVICES ACT 1998.pdf" \
  --title "Mental Health and Related Services Act 1998" \
  --type reference \
  --year "1998" \
  --description "Western Australian legislation governing mental health services"

echo ""
echo "========================================"
echo "✅ All 4 documents uploaded successfully!"
