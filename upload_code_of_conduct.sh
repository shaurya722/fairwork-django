#!/bin/bash
# Upload "Employee Code of Conduct" as a sample policy document.
# This script creates the policies/ directory + a realistic sample document,
# then runs the exact upload command you specified.

set -e

echo "==> Setting up policies directory..."
mkdir -p policies

# If you have the real PDF, put it here and comment out the sample creation below.
# Example:
#   cp "/path/to/real/Code_of_Conduct_v3.pdf" policies/Code_of_Conduct_v3.pdf

SAMPLE_FILE="policies/Code_of_Conduct_v3.txt"

if [ ! -f "$SAMPLE_FILE" ]; then
    echo "==> Creating sample Code of Conduct document (text format for testing)..."
    cat > "$SAMPLE_FILE" << 'EOF'
EMPLOYEE CODE OF CONDUCT
Version 3.0 - Effective 2025

1. PURPOSE
This Code of Conduct sets out the standards of behaviour expected from all employees,
contractors, and volunteers of the organisation.

2. CORE VALUES
We expect everyone to act with:
- Integrity and honesty
- Respect for others
- Accountability for their actions
- Commitment to a safe and inclusive workplace

3. PROFESSIONAL BEHAVIOUR
Employees must:
- Treat colleagues, clients, and stakeholders with dignity and respect
- Avoid any form of discrimination, harassment, or bullying
- Maintain confidentiality of sensitive information
- Declare and manage conflicts of interest
- Use company resources responsibly

4. SAFEGUARDING AND DUTY OF CARE
All staff working with vulnerable people (including NDIS participants, children,
and people with disability) must:
- Comply with all relevant legislation and organisational policies
- Report any concerns about safety or wellbeing immediately
- Maintain appropriate professional boundaries
- Complete required screening and training (e.g. NDIS Worker Screening Check)

5. GIFTS, BENEFITS AND HOSPITALITY
Employees must not:
- Accept gifts or benefits that could be perceived as influencing decisions
- Offer or accept bribes or kickbacks
- Use their position for personal gain

6. SOCIAL MEDIA AND PUBLIC COMMENTS
When using social media or speaking publicly:
- Do not disclose confidential client or organisational information
- Clearly state that views are personal (unless authorised to speak officially)
- Do not engage in conduct that could bring the organisation into disrepute

7. REPORTING CONCERNS
Anyone who becomes aware of a breach of this Code must report it through the
appropriate channel (manager, HR, or the organisation's whistleblower process).
No person will be penalised for making a good-faith report.

8. CONSEQUENCES OF BREACH
Breaches of this Code may result in disciplinary action, up to and including
termination of employment or engagement.

9. RELATED POLICIES
- Workplace Health and Safety Policy
- Privacy and Confidentiality Policy
- Complaints and Feedback Policy
- Safeguarding and Child Protection Policy
- Conflict of Interest Policy

10. ACKNOWLEDGEMENT
All employees are required to read, understand, and sign this Code of Conduct
upon commencement and when it is updated.

Document Owner: Human Resources
Approved: Board of Directors
Review Date: 2026
EOF
    echo "==> Sample document created: $SAMPLE_FILE"
else
    echo "==> Using existing file: $SAMPLE_FILE"
fi

echo
echo "==> Uploading document to SQLite + Pinecone..."
python3 manage.py upload_document "$SAMPLE_FILE" \
  --title "Employee Code of Conduct" \
  --type policy \
  --year "2025" \
  --description "Updated code of conduct and ethics policy"

echo
echo "==> Done. The document is now in both the database and vector DB."
echo "    You can verify with:"
echo "    python3 manage.py shell -c \"from awards.models import Document; d=Document.objects.get(title='Employee Code of Conduct'); print('ID:', d.id, 'Namespace:', d.namespace)\""
