#!/usr/bin/env python3
"""
Debug script for text extraction
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import LLMService

def test_extraction(url):
    """Test the new parallel extraction with detailed output"""
    print(f"Testing parallel extraction from: {url}")
    print("=" * 60)
    
    llm_service = LLMService('ollama')
    
    try:
        # Test the new parallel extraction method
        print("Testing parallel extraction (newspaper3k + trafilatura + beautifulsoup)...")
        result = llm_service.extract_text_from_url(url)
        
        if result:
            print(f"✓ Parallel extraction successful: {len(result)} characters")
            print(f"Preview: {result[:300]}...")
            return result
        else:
            print("✗ Parallel extraction failed")
            return None
        
    except Exception as e:
        print(f"✗ Parallel extraction error: {e}")
        return None

def main():
    if len(sys.argv) != 2:
        print("Usage: python debug_extraction.py <URL>")
        print("Example: python debug_extraction.py https://example.com/article")
        sys.exit(1)
    
    url = sys.argv[1]
    result = test_extraction(url)
    
    if result:
        print(f"\n✓ SUCCESS: Extracted {len(result)} characters")
        print("\nFirst 500 characters:")
        print("-" * 50)
        print(result[:500])
        print("-" * 50)
    else:
        print("\n✗ FAILED: Could not extract meaningful content")

if __name__ == "__main__":
    main() 