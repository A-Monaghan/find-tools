#!/usr/bin/env python3
"""
FastAPI Text Body Relationship Extractor
Run script for the FastAPI version of the application
"""

import os
import sys
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    """Main function to run the FastAPI application"""
    
    # Configuration
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    reload = os.getenv('RELOAD', 'false').lower() == 'true'
    workers = int(os.getenv('WORKERS', '1'))
    
    print(f"🚀 Starting Text Body Relationship Extractor (FastAPI)")
    print(f"📍 Host: {host}")
    print(f"🔌 Port: {port}")
    print(f"🔄 Reload: {reload}")
    print(f"👥 Workers: {workers}")
    print(f"📚 API Documentation: http://{host}:{port}/docs")
    print(f"📖 ReDoc Documentation: http://{host}:{port}/redoc")
    print()
    
    openrouter_key = os.getenv('OPENROUTER_API_KEY')
    print("🔑 OpenRouter API key: " + ("✅ Set" if openrouter_key and openrouter_key != "your_openrouter_api_key_here" else "❌ Not set (set OPENROUTER_API_KEY)"))
    print()
    
    try:
        # Start the FastAPI server
        uvicorn.run(
            "app_fastapi:app",
            host=host,
            port=port,
            reload=reload,
            workers=workers if not reload else 1,  # Workers don't work with reload=True
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 Shutting down gracefully...")
    except Exception as e:
        print(f"❌ Failed to start server: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 