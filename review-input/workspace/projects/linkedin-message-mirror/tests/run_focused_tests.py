#!/usr/bin/env python3
"""Dependency-free focused test runner for the post-capture unit tests."""
import importlib.util
import tempfile
from pathlib import Path

TEST_FILE = Path(__file__).with_name("test_capture_linkedin_posts.py")
spec = importlib.util.spec_from_file_location("linkedin_post_tests", TEST_FILE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

tests = [(name, value) for name, value in vars(module).items() if name.startswith("test_") and callable(value)]
for name, test in tests:
    if "tmp_path" in test.__code__.co_varnames:
        with tempfile.TemporaryDirectory() as directory:
            test(Path(directory))
    else:
        test()
    print(f"PASS {name}")
print(f"{len(tests)}/{len(tests)} focused tests passed")
