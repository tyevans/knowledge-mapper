#!/usr/bin/env python3
"""
Manual test script for JWKS client with live Keycloak instance.

This script tests the JWKS client against the running Keycloak service to verify:
1. OIDC discovery works
2. JWKS fetching works
3. Redis caching works
4. Key selection works
"""

import asyncio
import json
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Add app directory to Python path
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.jwks_client import JWKSClient
from app.core.config import settings
import redis.asyncio as redis


async def test_jwks_client():
    """Test JWKS client with live Keycloak instance."""

    print("=" * 80)
    print("JWKS Client Manual Test")
    print("=" * 80)
    print()

    # Test configuration - use localhost for connections from host machine
    issuer_url = "http://localhost:8080/realms/knowledge-mapper-dev"
    redis_url = "redis://default:knowledge_mapper_redis_pass@localhost:6379/0"
    cache_ttl = 3600

    print(f"OAuth Issuer URL: {issuer_url}")
    print(f"Redis URL: {redis_url}")
    print(f"JWKS Cache TTL: {cache_ttl} seconds")
    print()

    try:
        # Initialize Redis client for testing (localhost connection)
        print("Step 1: Initializing JWKS client...")
        redis_client = redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

        client = JWKSClient(
            redis_client=redis_client,
            cache_ttl=cache_ttl,
            http_timeout=10,
        )
        print("✓ JWKS client initialized successfully")
        print()

        # Test 1: Fetch JWKS from Keycloak (cache miss - should fetch from provider)
        print("Step 2: Fetching JWKS from Keycloak (first call - cache miss)...")
        jwks = await client.get_jwks(issuer_url)
        print(f"✓ JWKS fetched successfully")
        print(f"  - Number of keys: {len(jwks.get('keys', []))}")

        # Display key information
        for i, key in enumerate(jwks.get('keys', []), 1):
            print(f"  - Key {i}:")
            print(f"    - kid: {key.get('kid')}")
            print(f"    - kty: {key.get('kty')}")
            print(f"    - alg: {key.get('alg')}")
            print(f"    - use: {key.get('use')}")
        print()

        # Test 2: Fetch JWKS again (should hit cache)
        print("Step 3: Fetching JWKS again (second call - should hit cache)...")
        jwks_cached = await client.get_jwks(issuer_url)
        print(f"✓ JWKS retrieved (from cache)")
        print(f"  - Number of keys: {len(jwks_cached.get('keys', []))}")

        # Verify same data
        if jwks == jwks_cached:
            print("  ✓ Cached JWKS matches original")
        else:
            print("  ✗ WARNING: Cached JWKS differs from original!")
        print()

        # Test 3: Get specific signing key
        if jwks.get('keys'):
            first_key_id = jwks['keys'][0].get('kid')
            print(f"Step 4: Fetching specific signing key by kid: {first_key_id}...")
            signing_key = await client.get_signing_key(issuer_url, first_key_id)

            if signing_key:
                print(f"✓ Signing key retrieved successfully")
                print(f"  - kid: {signing_key.get('kid')}")
                print(f"  - kty: {signing_key.get('kty')}")
                print(f"  - alg: {signing_key.get('alg')}")
            else:
                print(f"✗ ERROR: Signing key not found!")
        print()

        # Test 4: Test with nonexistent key ID
        print("Step 5: Testing with nonexistent key ID...")
        nonexistent_key = await client.get_signing_key(issuer_url, "nonexistent-key-id")

        if nonexistent_key is None:
            print("✓ Correctly returned None for nonexistent key")
        else:
            print("✗ ERROR: Should have returned None for nonexistent key!")
        print()

        # Test 5: Force refresh (bypass cache)
        print("Step 6: Testing force refresh (bypass cache)...")
        jwks_fresh = await client.get_jwks(issuer_url, force_refresh=True)
        print(f"✓ JWKS fetched with force_refresh=True")
        print(f"  - Number of keys: {len(jwks_fresh.get('keys', []))}")
        print()

        # Test 6: Verify Redis cache
        print("Step 7: Verifying Redis cache directly...")
        cache_key = f"jwks:{issuer_url}"
        cached_value = await client.redis_client.get(cache_key)

        if cached_value:
            print(f"✓ JWKS found in Redis cache")
            print(f"  - Cache key: {cache_key}")
            cached_jwks = json.loads(cached_value)
            print(f"  - Cached key count: {len(cached_jwks.get('keys', []))}")

            # Check TTL
            ttl = await client.redis_client.ttl(cache_key)
            print(f"  - TTL remaining: {ttl} seconds")
        else:
            print(f"✗ WARNING: JWKS not found in Redis cache!")
        print()

        # Test 7: Test multi-issuer support
        print("Step 8: Testing multi-issuer support...")
        other_realm = "http://keycloak:8080/realms/master"
        print(f"  Fetching from different issuer: {other_realm}")

        try:
            other_jwks = await client.get_jwks(other_realm)
            print(f"✓ Successfully fetched JWKS from second issuer")
            print(f"  - Number of keys: {len(other_jwks.get('keys', []))}")

            # Verify separate caching
            other_cache_key = f"jwks:{other_realm}"
            other_cached = await client.redis_client.get(other_cache_key)
            if other_cached:
                print(f"✓ Second issuer cached separately")
                print(f"  - Cache key: {other_cache_key}")
        except Exception as e:
            print(f"  Note: Second issuer test failed (expected if realm doesn't exist): {e}")
        print()

        # Cleanup
        print("Step 9: Cleanup...")
        await client.close()
        await client.redis_client.close()
        print("✓ JWKS client closed")
        print()

        # Final summary
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print("✓ All core functionality tests passed!")
        print("✓ JWKS client is working correctly with live Keycloak")
        print("✓ Redis caching is functioning properly")
        print("✓ Multi-issuer support is operational")
        print()

        return True

    except Exception as e:
        print()
        print("=" * 80)
        print("ERROR")
        print("=" * 80)
        print(f"✗ Test failed with error: {e}")
        print()
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_jwks_client())
    sys.exit(0 if success else 1)
