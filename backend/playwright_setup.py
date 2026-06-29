"""
One-time Playwright Chromium installer.
Run this before starting the app to install browser binaries.
Usage: python playwright_setup.py
"""
import subprocess
import sys


def main():
    print("Installing Playwright Chromium browser...")
    print("(one-time download, ~150MB, may take a few minutes)")
    print()

    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=False,
            check=False,
        )
        if result.returncode == 0:
            print()
            print("Chromium installed successfully.")
        else:
            print()
            print("Installation may have failed.")
            print("Try manually: playwright install chromium")
            print("Or download from: https://playwright.dev/python/docs/browsers")
    except FileNotFoundError:
        print("Playwright package not found. Install it first: pip install playwright")
        sys.exit(1)


if __name__ == "__main__":
    main()
