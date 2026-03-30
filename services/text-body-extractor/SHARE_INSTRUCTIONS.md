
# How to Use the Text Body Relationship Extractor

## Access the Application
🌐 **Application URL**: https://9748956c445a.ngrok-free.app

## API Documentation
📚 **Interactive Docs**: https://9748956c445a.ngrok-free.app/docs
📖 **ReDoc**: https://9748956c445a.ngrok-free.app/redoc

## How to Use

### 1. Web Interface
- Open https://9748956c445a.ngrok-free.app in your browser
- Use the web interface to analyze text or URLs

### 2. API Usage
You can also use the API directly:

```bash
# Test the API
curl https://9748956c445a.ngrok-free.app/

# Analyze text
curl -X POST https://9748956c445a.ngrok-free.app/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"model_type": "ollama", "text": "Apple Inc. was founded by Steve Jobs.", "input_mode": "text"}'

# Get available models
curl https://9748956c445a.ngrok-free.app/api/models
```

### 3. Python Client
```python
import requests

# Analyze text
response = requests.post(f"https://9748956c445a.ngrok-free.app/api/analyze", json={
    "model_type": "ollama",
    "text": "Apple Inc. was founded by Steve Jobs.",
    "input_mode": "text"
})

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
