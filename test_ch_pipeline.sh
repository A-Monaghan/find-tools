#!/bin/bash
# Quick test for CH pipeline. Restart backend first if you added /ch/jobs recently.
# Usage: ./test_ch_pipeline.sh [API_KEY]

BASE="${VITE_API_BASE_URL:-http://localhost:8010}"
API_KEY="${1:-}"

echo "=== CH Pipeline Test (base: $BASE) ==="

# 1. Health
echo -e "\n1. Health:"
curl -s "$BASE/health" | head -1

# 2. List jobs (empty initially)
echo -e "\n2. List jobs:"
curl -s "$BASE/ch/jobs" | head -5

# 3. Run pipeline (company number search)
echo -e "\n3. Run pipeline (company 00000006):"
BODY='{"search_type":"company_number","search_value":"00000006"}'
if [ -n "$API_KEY" ]; then
  curl -s -X POST "$BASE/ch/run" -H "Content-Type: application/json" -d "{\"search_type\":\"company_number\",\"search_value\":\"00000006\",\"api_key_override\":\"$API_KEY\"}"
else
  curl -s -X POST "$BASE/ch/run" -H "Content-Type: application/json" -d "$BODY"
fi | head -20

echo -e "\n4. List jobs again:"
curl -s "$BASE/ch/jobs" | head -10

echo -e "\nDone."
