"""Mock Claude CLI binary for integration tests.

This script is placed on PATH during tests and mimics the real Claude CLI behavior.
"""

import os
import sys


def main():
    """Mock Claude CLI that returns canned responses."""
    # Parse arguments (we accept them but don't need to use them all)
    args = sys.argv[1:]

    # Check for --version flag
    if "--version" in args:
        print("Claude CLI Mock 1.0.0 (for testing)")
        sys.exit(0)

    # Get response from environment or use default
    response = os.environ.get("MOCK_CLAUDE_RESPONSE", '{"result": "mocked response"}')
    exit_code = int(os.environ.get("MOCK_CLAUDE_EXIT_CODE", "0"))

    # Print response to stdout
    print(response)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
