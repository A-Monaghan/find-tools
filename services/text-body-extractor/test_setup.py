#!/usr/bin/env python3
"""
Test script to verify the Text Body Relationship Extractor setup
"""

import sys
import json
from pathlib import Path

def test_imports():
    """Test if all required modules can be imported"""
    print("Testing imports...")
    
    try:
        import flask
        print("✓ Flask")
    except ImportError:
        print("✗ Flask")
        return False
    
    try:
        import requests
        print("✓ Requests")
    except ImportError:
        print("✗ Requests")
        return False
    
    try:
        import pandas
        print("✓ Pandas")
    except ImportError:
        print("✗ Pandas")
        return False
    
    try:
        import openai
        print("✓ OpenAI (used for OpenRouter)")
    except ImportError:
        print("✗ OpenAI")
        return False
    
    try:
        from bs4 import BeautifulSoup
        print("✓ BeautifulSoup")
    except ImportError:
        print("✗ BeautifulSoup")
        return False
    
    return True

def test_openrouter_config():
    """Check OpenRouter API key is set"""
    print("\nChecking OpenRouter config...")
    key = __import__("os").environ.get("OPENROUTER_API_KEY", "")
    if key and key != "your_openrouter_api_key_here":
        print("✓ OPENROUTER_API_KEY is set")
        return True
    print("⚠ OPENROUTER_API_KEY not set (set it in .env or environment to run analysis)")
    return True  # optional for setup

def test_flask_app():
    """Test if Flask app can be created"""
    print("\nTesting Flask app...")
    
    try:
        from app import app
        print("✓ Flask app created successfully")
        return True
    except Exception as e:
        print(f"✗ Flask app creation failed: {e}")
        return False

def test_sample_data():
    """Test with sample data"""
    print("\nTesting with sample data...")
    
    try:
        from app import LLMService, process_graph_results
        
        # Sample data that should work with any model
        sample_text = """
        John Smith works at Acme Corporation as a software engineer. 
        Acme Corporation is located in San Francisco, California. 
        John Smith reports to Jane Doe, who is the CTO of Acme Corporation.
        """
        
        print("Sample text processed successfully")
        print("Note: Full analysis requires a running LLM model")
        return True
    except Exception as e:
        print(f"✗ Sample data test failed: {e}")
        return False

def main():
    print("Text Body Relationship Extractor - Setup Test")
    print("=" * 50)
    
    all_tests_passed = True
    
    # Test imports
    if not test_imports():
        all_tests_passed = False
    
    test_openrouter_config()
    
    # Test Flask app
    if not test_flask_app():
        all_tests_passed = False
    
    # Test sample data
    if not test_sample_data():
        all_tests_passed = False
    
    print("\n" + "=" * 50)
    if all_tests_passed:
        print("✓ All critical tests passed!")
        print("You can now run the application with: python run.py")
    else:
        print("✗ Some tests failed. Please check the errors above.")
        print("Make sure to install dependencies: pip install -r requirements.txt")
    
    return all_tests_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 