#!/usr/bin/env python3
"""
Test script to debug Ollama extraction issues
"""

import os
import sys
import json
import re
from app import LLMService, Config

def test_ollama_extraction():
    """Test Ollama extraction with a simple text"""
    
    # Test text
    test_text = """
    John Smith is the CEO of TechCorp, a technology company based in San Francisco. 
    He works with Sarah Johnson, who is the CTO. The company was founded in 2010 
    and has offices in New York and London. Mary Wilson is the CFO and reports to John.
    """
    
    print("Testing Ollama extraction...")
    print(f"Test text: {test_text.strip()}")
    print("-" * 50)
    
    # Initialize LLM service
    llm_service = LLMService('ollama', base_url=Config.OLLAMA_BASE_URL)
    
    try:
        # Extract graph data
        result = llm_service.extract_graph_data(test_text)
        
        print("Extraction result:")
        print(json.dumps(result, indent=2))
        
        # Check if we got any relationships
        if result.get('relationships'):
            print(f"\n✓ Found {len(result['relationships'])} relationships")
        else:
            print("\n✗ No relationships found")
            
        if result.get('entities'):
            print(f"✓ Found {len(result['entities'])} entities")
        else:
            print("✗ No entities found")
            
    except Exception as e:
        print(f"Error during extraction: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ollama_extraction() 