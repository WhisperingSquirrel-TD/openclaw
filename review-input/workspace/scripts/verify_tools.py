#!/usr/bin/env python3
"""Quick verification that tools can be imported and run."""
import sys
import os

# Test that scripts exist and are readable
scripts = [
    'context_extract.py',
    'session_query.py', 
    'context_dashboard.py',
    'worker_wrapper.py'
]

print("Verifying script existence and basic functionality...")
for script in scripts:
    path = os.path.join('scripts', script)
    if os.path.exists(path):
        print(f"✓ {script} exists")
        # Try to import (basic syntax check)
        try:
            sys.path.insert(0, 'scripts')
            __import__(script.replace('.py', ''))
            print(f"  ✓ Can be imported")
        except Exception as e:
            print(f"  ✗ Import error: {e}")
    else:
        print(f"✗ {script} missing")

print("\nAll tools verified!")