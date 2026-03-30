# Text Body Relationship Extractor (Python)

A Python application that extracts entities and relationships from text content using multiple LLM models. Available in both **Flask** and **FastAPI** versions.

## Features

- **Multiple LLM Support**: OpenRouter (default), Ollama (local), Google Gemini, or OpenAI models
- **Text Extraction**: Extract main content from URLs using web scraping
- **Entity Recognition**: Identify people, organizations, locations, and concepts
- **Relationship Mapping**: Discover connections between entities
- **CSV Export**: Download results in Neo4j-compatible format
- **Modern UI**: Clean, responsive interface built with Tailwind CSS
- **API Documentation**: Automatic OpenAPI/Swagger documentation (FastAPI version)

## Prerequisites

- Python 3.8 or higher
- Ollama (for local models) - [Install Ollama](https://ollama.ai/)
- API keys for online models (optional)

## Installation

1. **Clone or download the project files**

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables** (optional):
   Copy `.env.example` to `.env` and fill in your keys. For OpenRouter (default), get a key at [openrouter.ai/keys](https://openrouter.ai/keys).
   ```env
   OPENROUTER_API_KEY=your_openrouter_api_key_here
   OPENROUTER_DEFAULT_MODEL=openai/gpt-4o-mini
   GEMINI_API_KEY=your_gemini_api_key_here
   OPENAI_API_KEY=your_openai_api_key_here
   OLLAMA_BASE_URL=http://localhost:11434
   DEFAULT_OLLAMA_MODEL=llama3.2
   ```

4. **Install Ollama models** (for local processing):
   ```bash
   # Install default models
   ollama pull llama3.2
   ollama pull llama3.1
   ollama pull mistral
   ollama pull codellama
   ```

## Usage

### FastAPI Version (Recommended)

The FastAPI version offers better performance, automatic API documentation, and modern Python features.

1. **Start the FastAPI application**:
   ```bash
   python run_fastapi.py
   ```

2. **Access the application**:
   - **Web Interface**: `http://localhost:5000`
   - **API Documentation**: `http://localhost:5000/docs`
   - **ReDoc Documentation**: `http://localhost:5000/redoc`

3. **Test the API**:
   ```bash
   python test_fastapi.py
   ```

### Flask Version

The original Flask version is still available for compatibility.

1. **Start the Flask application**:
   ```bash
   python run.py
   ```

2. **Open your browser** and navigate to `http://localhost:5000`

### Configuration

1. **Configure your model**:
   - **Ollama (Local)**: No API key required, select your preferred model
   - **Google Gemini**: Enter your Gemini API key
   - **OpenAI**: Enter your OpenAI API key

2. **Choose input method**:
   - **URL**: Enter a website URL to extract and analyze content
   - **Text**: Paste or type text directly

3. **Analyze content**: Click "Extract Relationships" to process your content

4. **View results**: Entities and relationships will be displayed in tables

5. **Export data**: Download CSV files for use in Neo4j or other graph databases

## Model Configuration

### Ollama (Local Models)
- **llama3.2**: Latest Llama model (recommended)
- **llama3.1**: Previous Llama version
- **mistral**: Fast and efficient model
- **codellama**: Specialized for code analysis

### Online Models
- **Google Gemini**: Requires API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
- **OpenAI**: Requires API key from [OpenAI Platform](https://platform.openai.com/api-keys)

## API Endpoints

### FastAPI Version
- `GET /`: API information and documentation links
- `POST /api/analyze`: Analyze text/URL content
- `POST /api/download/{file_type}`: Download CSV files (entities/relationships)
- `GET /api/models`: Get available Ollama models
- `GET /docs`: Interactive API documentation (Swagger UI)
- `GET /redoc`: Alternative API documentation (ReDoc)

### Flask Version
- `GET /`: Main application interface
- `POST /api/analyze`: Analyze text/URL content
- `POST /api/download/<file_type>`: Download CSV files (entities/relationships)
- `GET /api/models`: Get available Ollama models

## Output Format

### Entities CSV
```csv
entityId:ID,name,:LABEL
john_doe,John Doe,Person
acme_corp,Acme Corp,Company
```

### Relationships CSV
```csv
:START_ID,:END_ID,:TYPE
john_doe,acme_corp,WORKS_FOR
```

## File Structure

```
├── app_fastapi.py        # FastAPI application (recommended)
├── run_fastapi.py        # FastAPI run script
├── test_fastapi.py       # FastAPI test script
├── app.py                # Flask application (legacy)
├── run.py                # Flask run script
├── requirements.txt      # Python dependencies
├── README.md            # This file
├── .env                 # Environment variables (create this)
└── templates/
    └── index.html       # Web interface
```

## FastAPI vs Flask Comparison

| Feature | FastAPI | Flask |
|---------|---------|-------|
| Performance | ⭐⭐⭐⭐⭐ (Async support) | ⭐⭐⭐ (Synchronous) |
| API Documentation | ⭐⭐⭐⭐⭐ (Automatic) | ⭐⭐ (Manual) |
| Type Safety | ⭐⭐⭐⭐⭐ (Pydantic) | ⭐⭐ (Basic) |
| Modern Python | ⭐⭐⭐⭐⭐ (3.8+ features) | ⭐⭐⭐ (Compatible) |
| Learning Curve | ⭐⭐⭐⭐ (Easy) | ⭐⭐⭐⭐⭐ (Very Easy) |
| Ecosystem | ⭐⭐⭐⭐ (Growing) | ⭐⭐⭐⭐⭐ (Mature) |

## Troubleshooting

### Common Issues

1. **Ollama connection failed**:
   - Ensure Ollama is running: `ollama serve`
   - Check if models are installed: `ollama list`

2. **API key errors**:
   - Verify your API keys are correct
   - Check if you have sufficient credits/quota

3. **URL extraction fails**:
   - Some websites block automated access
   - Try using the text input mode instead

4. **Model not responding**:
   - For Ollama: Check if the model is downloaded
   - For online models: Verify API key and internet connection

### Performance Tips

- Use Ollama for faster local processing
- Gemini and OpenAI provide more accurate results but require internet
- Large texts may take longer to process
- Consider breaking very long texts into smaller chunks
- FastAPI version offers better performance for concurrent requests

## Development

### FastAPI Development
```bash
# Run with auto-reload
export RELOAD=true
python run_fastapi.py

# Run with multiple workers
export WORKERS=4
python run_fastapi.py
```

### Flask Development
```bash
export FLASK_ENV=development
python app.py
```

## Testing

### FastAPI Tests
```bash
# Start the server first
python run_fastapi.py

# In another terminal, run tests
python test_fastapi.py
```

### Flask Tests
```bash
# Start the server first
python run.py

# In another terminal, run tests
python test_api.py
```

## License

This project is open source and available under the MIT License.
