#!/usr/bin/env python3
"""
Text Body Relationship Extractor - Startup Script
"""

import os
import sys
import argparse
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import flask
        import requests
        import pandas
        import openai
        from bs4 import BeautifulSoup
        print("✓ All dependencies are installed")
        return True
    except ImportError as e:
        print(f"✗ Missing dependency: {e}")
        print("Please run: pip install -r requirements.txt")
        return False

def main():
    print("Text Body Relationship Extractor")
    print("=" * 40)
    
    parser = argparse.ArgumentParser(description="Start the Text Body Relationship Extractor Flask app.")
    parser.add_argument('--port', type=int, help='Port to run the server on (default: 5000 or $PORT env)')
    args = parser.parse_args()

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Determine port
    port = args.port or int(os.environ.get('PORT', 5000))
    print(f"\nStarting Flask application on port {port}...")
    print(f"Open your browser to: http://localhost:{port}")
    print("Press Ctrl+C to stop the server")
    print("-" * 40)
    
    # Start the Flask app
    try:
        from app import app
        app.run(debug=True, host='0.0.0.0', port=port)
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 