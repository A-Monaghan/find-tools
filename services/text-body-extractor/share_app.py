#!/usr/bin/env python3
"""
Share FastAPI Application Remotely
This script helps you share your Text Body Relationship Extractor with others
"""

import subprocess
import time
import requests
import json
import sys
import os
from pathlib import Path

def check_ngrok():
    """Check if ngrok is available"""
    try:
        result = subprocess.run(['ngrok', 'version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ ngrok is installed and working")
            return True
        else:
            print("❌ ngrok is not working properly")
            return False
    except FileNotFoundError:
        print("❌ ngrok not found. Please install it first:")
        print("   brew install ngrok/ngrok/ngrok")
        return False

def check_server_running(port=5000):
    """Check if the FastAPI server is running"""
    try:
        response = requests.get(f"http://localhost:{port}/", timeout=5)
        if response.status_code == 200:
            print(f"✅ FastAPI server is running on port {port}")
            return True
        else:
            print(f"❌ Server responded with status {response.status_code}")
            return False
    except requests.exceptions.RequestException:
        print(f"❌ Cannot connect to server on port {port}")
        print("   Make sure to start the server first:")
        print("   python run_fastapi.py")
        return False

def start_ngrok_tunnel(port=5000):
    """Start ngrok tunnel to the specified port"""
    print(f"🚀 Starting ngrok tunnel to port {port}...")
    print("   This will create a public URL for your application")
    print()
    
    try:
        # Start ngrok in the background
        process = subprocess.Popen(
            ['ngrok', 'http', str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait a moment for ngrok to start
        time.sleep(3)
        
        # Get the public URL from ngrok API
        try:
            response = requests.get('http://localhost:4040/api/tunnels', timeout=5)
            if response.status_code == 200:
                tunnels = response.json()['tunnels']
                if tunnels:
                    public_url = tunnels[0]['public_url']
                    print("🎉 Success! Your application is now accessible at:")
                    print(f"   🌐 {public_url}")
                    print()
                    print("📋 Share this URL with others to access your application")
                    print("📚 API Documentation: " + public_url + "/docs")
                    print("📖 ReDoc Documentation: " + public_url + "/redoc")
                    print()
                    print("⚠️  Important notes:")
                    print("   • This URL will change each time you restart ngrok")
                    print("   • Anyone with this URL can access your application")
                    print("   • Keep your API keys secure")
                    print("   • Press Ctrl+C to stop the tunnel")
                    print()
                    
                    return process, public_url
                else:
                    print("❌ No tunnels found")
                    process.terminate()
                    return None, None
            else:
                print("❌ Could not get tunnel information")
                process.terminate()
                return None, None
        except requests.exceptions.RequestException:
            print("❌ Could not connect to ngrok API")
            process.terminate()
            return None, None
            
    except Exception as e:
        print(f"❌ Failed to start ngrok: {str(e)}")
        return None, None

def test_remote_access(url):
    """Test if the remote URL is accessible"""
    print("🔍 Testing remote access...")
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            print("✅ Remote access is working!")
            return True
        else:
            print(f"❌ Remote access failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Remote access failed: {str(e)}")
        return False

def create_share_instructions(url):
    """Create instructions for sharing"""
    instructions = f"""
# How to Use the Text Body Relationship Extractor

## Access the Application
🌐 **Application URL**: {url}

## API Documentation
📚 **Interactive Docs**: {url}/docs
📖 **ReDoc**: {url}/redoc

## How to Use

### 1. Web Interface
- Open {url} in your browser
- Use the web interface to analyze text or URLs

### 2. API Usage
You can also use the API directly:

```bash
# Test the API
curl {url}/

# Analyze text
curl -X POST {url}/api/analyze \\
  -H "Content-Type: application/json" \\
  -d '{{"model_type": "ollama", "text": "Apple Inc. was founded by Steve Jobs.", "input_mode": "text"}}'

# Get available models
curl {url}/api/models
```

### 3. Python Client
```python
import requests

# Analyze text
response = requests.post(f"{url}/api/analyze", json={{
    "model_type": "ollama",
    "text": "Apple Inc. was founded by Steve Jobs.",
    "input_mode": "text"
}})

data = response.json()
print(data)
```

## Available Models
- **Ollama (Local)**: No API key required
- **Google Gemini**: Requires API key
- **OpenAI**: Requires API key

## Features
- Extract entities and relationships from text
- Analyze content from URLs
- Download results as CSV files
- Neo4j-compatible output format

## Notes
- This is a temporary URL that may change
- The application is running on a remote server
- Keep any API keys secure
"""
    
    # Save instructions to file
    with open('SHARE_INSTRUCTIONS.md', 'w') as f:
        f.write(instructions)
    
    print("📄 Instructions saved to SHARE_INSTRUCTIONS.md")
    print("   Share this file along with the URL")

def main():
    """Main function"""
    print("🌐 Share FastAPI Application Remotely")
    print("=" * 50)
    print()
    
    # Check prerequisites
    if not check_ngrok():
        return False
    
    if not check_server_running():
        return False
    
    print()
    
    # Start ngrok tunnel
    process, public_url = start_ngrok_tunnel()
    
    if not process or not public_url:
        print("❌ Failed to start ngrok tunnel")
        return False
    
    # Test remote access
    if test_remote_access(public_url):
        print()
        create_share_instructions(public_url)
        print()
        print("🎉 Your application is ready to share!")
        print("   Share the URL and instructions with others")
        print()
        print("Press Ctrl+C to stop the tunnel when done...")
        
        try:
            # Keep the tunnel running
            process.wait()
        except KeyboardInterrupt:
            print("\n🛑 Stopping ngrok tunnel...")
            process.terminate()
            print("✅ Tunnel stopped")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0) 