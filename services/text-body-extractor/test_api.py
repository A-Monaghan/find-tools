#!/usr/bin/env python3
"""
Test the API endpoint with OpenRouter (set OPENROUTER_API_KEY).
"""

import os
import requests
import json

def test_api_extraction():
    """Test the API extraction endpoint"""
    url = "http://localhost:8081/api/analyze"
    
    # Test data (OpenRouter; set OPENROUTER_API_KEY env or pass below)
    test_data = {
        "api_key": os.environ.get("OPENROUTER_API_KEY", ""),
        "url": "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "text": "",
        "input_mode": "url"
    }
    
    print("Testing API extraction...")
    print(f"URL: {test_data['url']}")
    print("=" * 50)
    
    try:
        response = requests.post(url, json=test_data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                data = result.get('data', {})
                entities = data.get('entities', [])
                relationships = data.get('relationships', [])
                extracted_text = result.get('extracted_text', '')
                
                print("✓ API call successful!")
                print(f"Extracted text length: {len(extracted_text)} characters")
                print(f"Entities found: {len(entities)}")
                print(f"Relationships found: {len(relationships)}")
                
                print("\nFirst 200 characters of extracted text:")
                print("-" * 40)
                print(extracted_text[:200] + "..." if len(extracted_text) > 200 else extracted_text)
                print("-" * 40)
                
                if entities:
                    print(f"\nSample entities:")
                    for i, entity in enumerate(entities[:5]):
                        print(f"  {i+1}. {entity['name']} ({entity['label']})")
                
                if relationships:
                    print(f"\nSample relationships:")
                    for i, rel in enumerate(relationships[:5]):
                        print(f"  {i+1}. {rel['source']} --{rel['type']}--> {rel['target']}")
                
            else:
                print(f"✗ API returned error: {result.get('error', 'Unknown error')}")
        else:
            print(f"✗ HTTP error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.Timeout:
        print("✗ Request timed out")
    except requests.exceptions.ConnectionError:
        print("✗ Connection error - make sure the app is running on port 8081")
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == "__main__":
    test_api_extraction() 