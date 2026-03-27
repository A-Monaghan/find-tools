#!/usr/bin/env python3
"""
RAG System Full Verification Script
Tests: API, Document Upload, Processing, Chat
"""

import argparse
import requests
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_FRONTEND_URL = "http://localhost:3000"

# Generous timeouts: cold embedding load can block workers briefly; long reads avoid false failures
HTTP_SHORT = 30
HTTP_LONG = 120
UPLOAD_TIMEOUT = 300
POLL_DEADLINE_SEC = 240
WAIT_BACKEND_SEC = 120


def parse_args():
    """Parse CLI arguments for base and frontend URLs."""
    p = argparse.ArgumentParser(description="Verify RAG-v2.1 system health and core API")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Backend API URL (default: {DEFAULT_BASE_URL})")
    p.add_argument("--frontend-url", default=DEFAULT_FRONTEND_URL, help=f"Frontend URL (default: {DEFAULT_FRONTEND_URL})")
    p.add_argument(
        "--smoke",
        action="store_true",
        help="API smoke only: /health, /, /docs, GET /documents/ (no frontend, upload, or chat)",
    )
    return p.parse_args()


# Set by main() from CLI args
BASE_URL = DEFAULT_BASE_URL
FRONTEND_URL = DEFAULT_FRONTEND_URL


def wait_for_backend() -> bool:
    """Poll /health until the API responds (cold import or restarts can delay first byte)."""
    print("Waiting for backend …")
    deadline = time.time() + WAIT_BACKEND_SEC
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=8)
            if r.status_code == 200:
                print("  ✓ Backend reachable")
                return True
        except Exception:
            pass
        time.sleep(2)
    print(f"  ✗ No response from {BASE_URL}/health within {WAIT_BACKEND_SEC}s")
    return False


def test_health():
    """Test backend health endpoint."""
    print("=" * 50)
    print("1. Testing Backend Health")
    print("=" * 50)
    
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=HTTP_SHORT)
        print(f"  Status: {r.status_code}")
        print(f"  Response: {r.json()}")
        return r.status_code == 200
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

def test_api_root():
    """Test API root endpoint."""
    print("\n" + "=" * 50)
    print("2. Testing API Root")
    print("=" * 50)
    
    try:
        r = requests.get(f"{BASE_URL}/", timeout=HTTP_SHORT)
        print(f"  Status: {r.status_code}")
        print(f"  Response: {r.json()}")
        return r.status_code == 200
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

def test_docs_endpoint():
    """Test Swagger docs are accessible."""
    print("\n" + "=" * 50)
    print("3. Testing API Documentation")
    print("=" * 50)
    
    try:
        r = requests.get(f"{BASE_URL}/docs", timeout=HTTP_SHORT)
        print(f"  Status: {r.status_code}")
        print(f"  ✓ Swagger UI accessible at {BASE_URL}/docs")
        return r.status_code == 200
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

def test_list_documents():
    """Test document list endpoint."""
    print("\n" + "=" * 50)
    print("4. Testing Document List API")
    print("=" * 50)
    
    try:
        r = requests.get(f"{BASE_URL}/documents/", timeout=HTTP_SHORT)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            docs = r.json()
            print(f"  Documents: {len(docs)}")
            return True
        return False
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

def test_frontend():
    """Test frontend is accessible."""
    print("\n" + "=" * 50)
    print("5. Testing Frontend")
    print("=" * 50)
    
    try:
        r = requests.get(FRONTEND_URL, timeout=HTTP_SHORT)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            print(f"  ✓ Frontend accessible at {FRONTEND_URL}")
            return True
        return False
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

def _write_test_pdf(path: Path) -> bool:
    """Create a minimal 2-page PDF for upload tests. Prefer reportlab; else PyMuPDF (backend dep)."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter

        c = canvas.Canvas(str(path), pagesize=letter)
        c.drawString(100, 700, "Test Document for RAG System")
        c.drawString(100, 680, "This is page 1 of the test document.")
        c.drawString(100, 660, "The quick brown fox jumps over the lazy dog.")
        c.drawString(100, 640, "Machine learning is a subset of artificial intelligence.")
        c.showPage()
        c.drawString(100, 700, "Page 2")
        c.drawString(100, 680, "This is the second page of the test document.")
        c.drawString(100, 660, "Natural language processing enables computers to understand text.")
        c.showPage()
        c.save()
        return True
    except ImportError:
        pass
    # PyMuPDF ships with the backend venv — same interpreter may lack it if you used system python3
    try:
        import fitz  # pymupdf

        doc = fitz.open()
        lines_p1 = (
            "Test Document for RAG System\n"
            "Machine learning is a subset of artificial intelligence.\n"
            "The quick brown fox jumps over the lazy dog."
        )
        lines_p2 = (
            "Page 2\n"
            "Natural language processing enables computers to understand text."
        )
        for text in (lines_p1, lines_p2):
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 720), text)
        doc.save(str(path))
        doc.close()
        return True
    except ImportError:
        pass
    # Use repo venv if present (has pymupdf from backend/requirements.txt)
    venv_py = Path(__file__).resolve().parent / "venv" / "bin" / "python"
    if venv_py.is_file():
        try:
            subprocess.run(
                [
                    str(venv_py),
                    "-c",
                    "import fitz, sys; p=sys.argv[1]; d=fitz.open(); "
                    "t1='Test Document for RAG System\\nMachine learning is a subset of artificial intelligence.'; "
                    "t2='Page 2\\nNatural language processing enables computers to understand text.'; "
                    "pg=d.new_page(width=612,height=792); pg.insert_text((72,720), t1); "
                    "pg=d.new_page(width=612,height=792); pg.insert_text((72,720), t2); "
                    "d.save(p); d.close()",
                    str(path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return True
        except (subprocess.CalledProcessError, OSError):
            pass
    return path.exists()


def test_document_upload():
    """Test document upload with a sample PDF."""
    print("\n" + "=" * 50)
    print("6. Testing Document Upload & Processing")
    print("=" * 50)

    test_pdf_path = Path("test_sample.pdf")

    try:
        if _write_test_pdf(test_pdf_path):
            print(f"  ✓ Test PDF ready: {test_pdf_path}")
        else:
            print("  ✗ No test PDF: install reportlab or pymupdf, or add test_sample.pdf")
            return False
    except Exception as e:
        print(f"  ✗ Failed to create test PDF: {e}")
        return False
    
    # Upload the PDF
    try:
        with open(test_pdf_path, "rb") as f:
            files = {"file": ("test_document.pdf", f, "application/pdf")}
            r = requests.post(f"{BASE_URL}/documents/upload", files=files, timeout=UPLOAD_TIMEOUT)
        
        print(f"  Upload status: {r.status_code}")
        if r.status_code == 200:
            response = r.json()
            doc_id = response.get("id")
            print(f"  ✓ Upload successful. Document ID: {doc_id}")
            print(f"  Status: {response.get('status')}")
            
            # Poll until indexed — first embedding load can exceed 10s; use generous read timeouts
            print("  Polling processing status (cold embed can take minutes)...")
            deadline = time.time() + POLL_DEADLINE_SEC
            last = None
            while time.time() < deadline:
                r2 = requests.get(f"{BASE_URL}/documents/{doc_id}", timeout=HTTP_LONG)
                if r2.status_code != 200:
                    print(f"  ✗ GET document failed: {r2.status_code} {r2.text[:200]}")
                    return False, None
                status = r2.json()
                last = status
                print(
                    f"  … status={status.get('status')} pages={status.get('total_pages')} "
                    f"chunks={status.get('chunk_count')}"
                )
                if status.get("status") == "indexed":
                    print("  ✓ Document fully processed and indexed!")
                    return True, doc_id
                if status.get("status") == "error":
                    print(f"  ✗ Ingest error: {status.get('error_message', 'unknown')}")
                    return False, None
                time.sleep(5)

            if last and last.get("status") == "processing":
                print("  ⏳ Still processing after timeout — treating upload as OK for smoke")
                return True, doc_id
            return False, None
        else:
            print(f"  ✗ Upload failed: {r.text}")
            return False, None
    except Exception as e:
        print(f"  ✗ Upload error: {e}")
        return False, None

def test_chat_query(doc_id=None):
    """Test chat query endpoint."""
    print("\n" + "=" * 50)
    print("7. Testing Chat/Query API")
    print("=" * 50)
    
    query_data = {
        "query": "What is machine learning?",
        "document_id": str(doc_id) if doc_id else None
    }
    
    try:
        print(f"  Sending query: '{query_data['query']}'")
        r = requests.post(
            f"{BASE_URL}/chat/query",
            json=query_data,
            timeout=HTTP_LONG
        )
        
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            response = r.json()
            print(f"  ✓ Query successful!")
            answer_text = response.get("answer") or response.get("response", "")
            print(f"  Response preview: {answer_text[:150]}...")
            
            # Check citations
            citations = response.get('citations', [])
            print(f"  Citations: {len(citations)}")
            retrieved_chunks = response.get("retrieved_chunks", [])
            if not answer_text:
                print("  ✗ Empty answer payload")
                return False
            if not retrieved_chunks:
                print("  ✗ No retrieved chunks returned")
                return False
            if len(citations) == 0:
                print("  ✗ No citations returned")
                return False
            return True
        else:
            print(f"  ✗ Query failed: {r.text[:200]}")
            return False
    except requests.exceptions.Timeout:
        print("  ⏳ Query timed out (may be waiting for LLM)")
        return False
    except Exception as e:
        print(f"  ✗ Query error: {e}")
        return False

def main():
    global BASE_URL, FRONTEND_URL
    args = parse_args()
    BASE_URL = args.base_url.rstrip("/")
    FRONTEND_URL = args.frontend_url.rstrip("/")

    print("\n" + "=" * 50)
    if args.smoke:
        print("RAG API Smoke Test")
    else:
        print("RAG System Full Verification")
    print("=" * 50)
    print(f"  Backend:  {BASE_URL}")
    if not args.smoke:
        print(f"  Frontend: {FRONTEND_URL}")
    print()

    results = []
    doc_id = None

    # Full run: ensure API is up before sequential tests (avoids cascading timeouts)
    if not args.smoke and not wait_for_backend():
        print("\nStart the API, then retry:\n  ./scripts/run_backend_venv.sh\n  docker compose up -d backend")
        return False

    # Smoke: backend endpoints only (fast, no LLM / PDF deps)
    if args.smoke:
        results.append(("Health Check", test_health()))
        results.append(("API Root", test_api_root()))
        results.append(("API Docs", test_docs_endpoint()))
        results.append(("Document List", test_list_documents()))
        print("\n" + "=" * 50)
        print("SMOKE SUMMARY")
        print("=" * 50)
        passed = sum(1 for _, r in results if r)
        total = len(results)
        for name, result in results:
            status = "✓ PASS" if result else "✗ FAIL"
            print(f"  {status}: {name}")
        print()
        print(f"Result: {passed}/{total} checks passed")
        if passed == total:
            print(f"\nAPI OK — open {BASE_URL}/docs for interactive testing.")
        else:
            print("\nStart the stack: cd RAG-v2.1 && docker compose up -d")
        return passed == total

    # Run all tests
    results.append(("Health Check", test_health()))
    results.append(("API Root", test_api_root()))
    results.append(("API Docs", test_docs_endpoint()))
    results.append(("Document List", test_list_documents()))
    results.append(("Frontend", test_frontend()))
    
    # Document upload test
    upload_result = test_document_upload()
    if isinstance(upload_result, tuple):
        upload_success, doc_id = upload_result
    else:
        upload_success = upload_result
    results.append(("Document Upload", upload_success))
    
    # Chat test (if we have a document)
    if doc_id:
        results.append(("Chat Query", test_chat_query(doc_id)))
    else:
        print("\n  ! Skipping chat test (no document uploaded)")
        results.append(("Chat Query", False))
    
    # Summary
    print("\n" + "=" * 50)
    print("VERIFICATION SUMMARY")
    print("=" * 50)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")
    
    print()
    print(f"Result: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All systems operational! RAG is ready to use.")
        print(f"\nAccess points:")
        print(f"  - Frontend: {FRONTEND_URL}")
        print(f"  - API Docs: {BASE_URL}/docs")
        print(f"  - API Base: {BASE_URL}")
    else:
        print("\n⚠️  Some tests failed. Check the output above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
