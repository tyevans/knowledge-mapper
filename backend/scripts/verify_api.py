#!/usr/bin/env python3
"""
Simple script to verify API endpoints are working.
"""

import httpx
import json
import sys


def test_endpoint(client: httpx.Client, url: str, endpoint_name: str) -> bool:
    """Test a single endpoint."""
    try:
        response = client.get(url)
        if response.status_code == 200:
            print(f"✓ {endpoint_name}: OK")
            print(f"  Response: {json.dumps(response.json(), indent=2)}")
            return True
        else:
            print(f"✗ {endpoint_name}: Failed (status {response.status_code})")
            return False
    except Exception as e:
        print(f"✗ {endpoint_name}: Error - {e}")
        return False


def main():
    """Run API verification tests."""
    base_url = "http://localhost:8000"

    print(f"Testing API at {base_url}\n")

    with httpx.Client(base_url=base_url, timeout=5.0) as client:
        results = []

        # Test root endpoint
        results.append(test_endpoint(client, "/", "Root endpoint"))
        print()

        # Test health endpoint
        results.append(test_endpoint(client, "/api/v1/health", "Health check"))
        print()

        # Test readiness endpoint
        results.append(test_endpoint(client, "/api/v1/ready", "Readiness check"))
        print()

        # Summary
        passed = sum(results)
        total = len(results)
        print(f"\nResults: {passed}/{total} endpoints passed")

        if passed == total:
            print("All endpoints working correctly!")
            return 0
        else:
            print("Some endpoints failed!")
            return 1


if __name__ == "__main__":
    sys.exit(main())
