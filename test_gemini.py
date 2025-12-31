#!/usr/bin/env python3
"""
AegisAI - Gemini API Test Script

Tests the Gemini integration to verify it works correctly.

Usage:
    python test_gemini.py
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


def test_gemini():
    """Test Gemini API integration."""
    print("=" * 50)
    print("AegisAI - Gemini API Test")
    print("=" * 50)
    
    # Check API key
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        print("❌ GEMINI_API_KEY not set in .env")
        print("   Add: GEMINI_API_KEY=your-key-here")
        return False
    
    print(f"✓ API Key found: {api_key[:10]}...")
    
    try:
        from aegis.ai.gemini_client import GeminiClient, GeminiConfig
        
        config = GeminiConfig(
            api_key=api_key,
            model="gemini-2.0-flash-exp"
        )
        client = GeminiClient(config)
        
        print(f"✓ Client initialized with model: {config.model}")
        
        # Test 1: Simple generation
        print("\n--- Test 1: Simple Generation ---")
        response = client.generate("What is 2 + 2? Reply with just the number.")
        print(f"Response: {response.text}")
        print(f"Tokens: {response.total_tokens}")
        print(f"Latency: {response.latency_ms:.0f}ms")
        
        # Test 2: System prompt
        print("\n--- Test 2: With System Prompt ---")
        response = client.generate(
            prompt="What does AegisAI do?",
            system_prompt="You are AegisAI, a surveillance analytics system. Be brief."
        )
        print(f"Response: {response.text[:200]}...")
        
        # Test 3: JSON generation
        print("\n--- Test 3: JSON Generation ---")
        data = client.generate_json(
            "List 3 risk levels with colors in JSON: {levels: [{name, color}]}"
        )
        print(f"JSON: {data}")
        
        # Stats
        print("\n--- Client Stats ---")
        stats = client.get_stats()
        print(f"Total tokens used: {stats['total_tokens_used']}")
        print(f"Requests made: {stats['request_count']}")
        
        print("\n" + "=" * 50)
        print("✅ All tests passed! Gemini integration working.")
        print("=" * 50)
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_gemini()
    sys.exit(0 if success else 1)
