#!/usr/bin/env python3
"""
FastAPI Text Body Relationship Extractor - Demo Script
Demonstrates how to use the FastAPI endpoints programmatically
"""

import requests
import json
import sys

# Configuration
BASE_URL = "http://localhost:8081"

def demo_root_endpoint():
    """Demonstrate the root endpoint"""
    print("🌐 Root Endpoint Demo")
    print("-" * 40)
    
    response = requests.get(f"{BASE_URL}/")
    if response.status_code == 200:
        data = response.json()
        print(f"✅ API Info: {data['message']}")
        print(f"📋 Version: {data['version']}")
        print(f"📚 Docs: {BASE_URL}{data['docs']}")
        print(f"📖 ReDoc: {BASE_URL}{data['redoc']}")
    else:
        print(f"❌ Failed: {response.status_code}")
    print()

def demo_models_endpoint():
    """Demonstrate the models endpoint"""
    print("🤖 Models Endpoint Demo")
    print("-" * 40)
    
    response = requests.get(f"{BASE_URL}/api/models")
    if response.status_code == 200:
        data = response.json()
        models = data.get('models', [])
        print(f"✅ Found {len(models)} available models:")
        for i, model in enumerate(models, 1):
            print(f"   {i}. {model}")
    else:
        print(f"❌ Failed: {response.status_code}")
    print()

def demo_text_analysis():
    """Demonstrate text analysis"""
    print("📝 Text Analysis Demo")
    print("-" * 40)
    
    test_text = """
    Apple Inc. was founded by Steve Jobs and Steve Wozniak in 1976. 
    The company is headquartered in Cupertino, California. 
    Tim Cook is the current CEO of Apple. 
    Apple manufactures the iPhone, iPad, and Mac computers.
    """
    
    payload = {
        "model_type": "ollama",
        "text": test_text,
        "input_mode": "text"
    }
    
    print("🔍 Analyzing text with Ollama...")
    response = requests.post(f"{BASE_URL}/api/analyze", json=payload, timeout=60)
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            entities = data['data'].get('entities', [])
            relationships = data['data'].get('relationships', [])
            
            print(f"✅ Analysis successful!")
            print(f"📊 Found {len(entities)} entities and {len(relationships)} relationships")
            
            print("\n🏷️  Entities:")
            for entity in entities[:5]:  # Show first 5
                print(f"   • {entity['name']} ({entity['label']})")
            
            print("\n🔗 Relationships:")
            for rel in relationships[:5]:  # Show first 5
                print(f"   • {rel['source']} --[{rel['type']}]--> {rel['target']}")
        else:
            print(f"❌ Analysis failed: {data.get('error', 'Unknown error')}")
    else:
        print(f"❌ Request failed: {response.status_code}")
    print()

def demo_url_analysis():
    """Demonstrate URL analysis"""
    print("🌐 URL Analysis Demo")
    print("-" * 40)
    
    test_url = "https://en.wikipedia.org/wiki/Apple_Inc."
    
    payload = {
        "model_type": "ollama",
        "url": test_url,
        "input_mode": "url"
    }
    
    print(f"🔍 Analyzing URL: {test_url}")
    print("⏳ This may take a moment...")
    
    response = requests.post(f"{BASE_URL}/api/analyze", json=payload, timeout=120)
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            entities = data['data'].get('entities', [])
            relationships = data['data'].get('relationships', [])
            extracted_text = data.get('extracted_text', '')
            
            print(f"✅ URL analysis successful!")
            print(f"📄 Extracted {len(extracted_text)} characters of text")
            print(f"📊 Found {len(entities)} entities and {len(relationships)} relationships")
            
            print("\n🏷️  Sample Entities:")
            for entity in entities[:3]:
                print(f"   • {entity['name']} ({entity['label']})")
            
            print("\n🔗 Sample Relationships:")
            for rel in relationships[:3]:
                print(f"   • {rel['source']} --[{rel['type']}]--> {rel['target']}")
        else:
            print(f"❌ Analysis failed: {data.get('error', 'Unknown error')}")
    else:
        print(f"❌ Request failed: {response.status_code}")
    print()

def demo_csv_download():
    """Demonstrate CSV download"""
    print("📥 CSV Download Demo")
    print("-" * 40)
    
    # First, get some analysis data
    test_text = "Apple Inc. was founded by Steve Jobs in 1976."
    payload = {
        "model_type": "ollama",
        "text": test_text,
        "input_mode": "text"
    }
    
    response = requests.post(f"{BASE_URL}/api/analyze", json=payload, timeout=60)
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            analysis_data = data['data']
            
            # Download entities CSV
            print("📄 Downloading entities CSV...")
            entities_response = requests.post(
                f"{BASE_URL}/api/download/entities",
                json={"entities": analysis_data.get('entities', []), "relationships": []}
            )
            
            if entities_response.status_code == 200:
                print("✅ Entities CSV downloaded successfully")
                print(f"   Content-Type: {entities_response.headers.get('content-type')}")
                print(f"   Content-Length: {entities_response.headers.get('content-length')} bytes")
            else:
                print(f"❌ Entities download failed: {entities_response.status_code}")
            
            # Download relationships CSV
            print("📄 Downloading relationships CSV...")
            relationships_response = requests.post(
                f"{BASE_URL}/api/download/relationships",
                json={"entities": [], "relationships": analysis_data.get('relationships', [])}
            )
            
            if relationships_response.status_code == 200:
                print("✅ Relationships CSV downloaded successfully")
                print(f"   Content-Type: {relationships_response.headers.get('content-type')}")
                print(f"   Content-Length: {relationships_response.headers.get('content-length')} bytes")
            else:
                print(f"❌ Relationships download failed: {relationships_response.status_code}")
        else:
            print("❌ Need analysis data for download demo")
    else:
        print("❌ Failed to get analysis data for download demo")
    print()

def main():
    """Main demonstration function"""
    print("🚀 FastAPI Text Body Relationship Extractor - Demo")
    print("=" * 60)
    print()
    
    # Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code != 200:
            print(f"❌ Server not responding properly: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to server: {str(e)}")
        print("   Make sure the FastAPI server is running with: python run_fastapi.py")
        return False
    
    print("✅ Server is running and accessible")
    print()
    
    # Run demonstrations
    demo_root_endpoint()
    demo_models_endpoint()
    demo_text_analysis()
    demo_url_analysis()
    demo_csv_download()
    
    print("🎉 Demo completed!")
    print("\n💡 Next steps:")
    print("   • Visit http://localhost:8081/docs for interactive API documentation")
    print("   • Visit http://localhost:8081/redoc for alternative documentation")
    print("   • Use the API endpoints in your own applications")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 