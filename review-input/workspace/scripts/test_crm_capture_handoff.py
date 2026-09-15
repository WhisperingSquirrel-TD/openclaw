"""Compatibility test entrypoint; canonical focused tests live in tests/."""
import importlib.util
import sys
from pathlib import Path

TEST = Path(__file__).resolve().parents[1] / 'tests' / 'test_crm_capture_handoff.py'
spec = importlib.util.spec_from_file_location('canonical_crm_capture_tests', TEST)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)

if __name__ == '__main__':
    import unittest
    unittest.main(module=module)
