#!/usr/bin/env python3
"""
Test script for FastAPI Text Body Relationship Extractor
Tests all endpoints and functionality
"""

import os
import requests
import json
import time
import sys
from typing import Dict, Any

# Configuration (match run_fastapi.py default port)
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:5000")
TEST_TEXT = """
Apple Inc. was founded by Steve Jobs and Steve Wozniak in 1976. 
The company is headquartered in Cupertino, California. 
Tim Cook is the current CEO of Apple. 
Apple manufactures the iPhone, iPad, and Mac computers.
"""

def test_root_endpoint():
    """Test the root endpoint (serves HTML UI)"""
    print("🔍 Testing root endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/")
        if response.status_code == 200:
            # Root serves HTML; optional check for expected content
            if "text/html" in response.headers.get("Content-Type", ""):
                print("✅ Root endpoint working (HTML UI)")
            else:
                print("✅ Root endpoint working")
            return True
        else:
            print(f"❌ Root endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Root endpoint error: {str(e)}")
        return False

def test_analyze_endpoint(api_key: str = None):
    """Test the analyze endpoint with OpenRouter"""
    print("\n🔍 Testing analyze endpoint (OpenRouter)...")
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key or api_key == "your_openrouter_api_key_here":
        print("⏭️  Skipping (OPENROUTER_API_KEY not set)")
        return None
    payload = {
        "api_key": api_key,
        "text": TEST_TEXT,
        "input_mode": "text"
    }
    try:
        response = requests.post(
            f"{BASE_URL}/api/analyze",
            json=payload,
            timeout=60
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                entities = data['data'].get('entities', [])
                relationships = data['data'].get('relationships', [])
                print(f"✅ OpenRouter analysis successful:")
                print(f"   Entities found: {len(entities)}")
                print(f"   Relationships found: {len(relationships)}")
                if entities:
                    print(f"   Sample entities: {entities[:2]}")
                if relationships:
                    print(f"   Sample relationships: {relationships[:2]}")
                return data['data']
            else:
                print(f"❌ Analysis failed: {data.get('error', 'Unknown error')}")
                return None
        else:
            print(f"❌ Analysis failed: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Error: {error_data.get('detail', 'Unknown error')}")
            except Exception:
                print(f"   Error: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Analysis error: {str(e)}")
        return None

def test_download_endpoints(analysis_data: Dict[str, Any]):
    """Test the download endpoints"""
    print("\n🔍 Testing download endpoints...")
    
    if not analysis_data:
        print("❌ No analysis data available for download test")
        return False
    
    # Test entities download
    try:
        response = requests.post(
            f"{BASE_URL}/api/download/entities",
            json={"entities": analysis_data.get('entities', []), "relationships": []}
        )
        if response.status_code == 200:
            print("✅ Entities download working")
        else:
            print(f"❌ Entities download failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Entities download error: {str(e)}")
        return False
    
    # Test relationships download
    try:
        response = requests.post(
            f"{BASE_URL}/api/download/relationships",
            json={"entities": [], "relationships": analysis_data.get('relationships', [])}
        )
        if response.status_code == 200:
            print("✅ Relationships download working")
        else:
            print(f"❌ Relationships download failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Relationships download error: {str(e)}")
        return False
    
    return True

def test_url_extraction(api_key: str = None):
    """Test URL extraction functionality with OpenRouter"""
    print("\n🔍 Testing URL extraction...")
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key or api_key == "your_openrouter_api_key_here":
        print("⏭️  Skipping (OPENROUTER_API_KEY not set)")
        return True  # skip but don't fail
    test_url = "https://en.wikipedia.org/wiki/Apple_Inc."
    payload = {
        "api_key": api_key,
        "url": test_url,
        "input_mode": "url"
    }
    try:
        response = requests.post(
            f"{BASE_URL}/api/analyze",
            json=payload,
            timeout=120
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                entities = data['data'].get('entities', [])
                relationships = data['data'].get('relationships', [])
                extracted_text = data.get('extracted_text', '')
                
                print(f"✅ URL extraction successful:")
                print(f"   Extracted text length: {len(extracted_text)} characters")
                print(f"   Entities found: {len(entities)}")
                print(f"   Relationships found: {len(relationships)}")
                return True
            else:
                print(f"❌ URL extraction failed: {data.get('error', 'Unknown error')}")
                return False
        else:
            print(f"❌ URL extraction failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ URL extraction error: {str(e)}")
        return False

def main():
    """Main test function"""
    print("🧪 FastAPI Text Body Relationship Extractor - Test Suite")
    print("=" * 60)
    
    # Check if server is running (GET /api returns JSON)
    print("🔍 Checking if server is running...")
    try:
        response = requests.get(f"{BASE_URL}/api", timeout=5)
        if response.status_code == 200:
            print("✅ Server is running")
        else:
            print(f"❌ Server responded with status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to server: {str(e)}")
        print("   Make sure the FastAPI server is running with: python run_fastapi.py")
        return False
    
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    tests_passed = 0
    total_tests = 0
    
    total_tests += 1
    if test_root_endpoint():
        tests_passed += 1
    
    total_tests += 1
    analysis_data = test_analyze_endpoint(api_key)
    if analysis_data:
        tests_passed += 1
        total_tests += 1
        if test_download_endpoints(analysis_data):
            tests_passed += 1
    else:
        total_tests += 1  # count analyze as one test
    
    total_tests += 1
    if test_url_extraction(api_key):
        tests_passed += 1
    
    # Summary
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("🎉 All tests passed! FastAPI application is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 