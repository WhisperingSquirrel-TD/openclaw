#!/usr/bin/env python3
import tempfile
from pathlib import Path
from skill_library_release import *

with tempfile.TemporaryDirectory() as tmp:
    d = Path(tmp) / 'example'; d.mkdir()
    (d / 'SKILL.md').write_text('one')
    current = release_record('workspace-skills/example', d)
    assert permitted_pull(None, current) == 'new'
    assert permitted_pull(current['bundle_sha256'], current) == 'noop'
    (d / 'SKILL.md').write_text('two')
    changed = release_record('workspace-skills/example', d)
    assert permitted_pull(current['bundle_sha256'], changed) == 'update'
    manifest = manifest_template({'example': current})
    validate_manifest(manifest)
    assert manifest['schema_version'] == 3
    assert 'version' not in current
    legacy = dict(current); legacy['version'] = 1
    try: validate_release(legacy)
    except ValueError as e: assert 'no version counter' in str(e)
    else: raise AssertionError('version counters must be rejected')
    bad = {'schema_version': 3, 'skills': {'x': current, 'y': dict(current)}}
    try: validate_manifest(bad)
    except ValueError as e: assert 'duplicate' in str(e)
    else: raise AssertionError('duplicate canonical paths must fail closed')
print('PASS: new, update, noop, hash integrity, no version counters, manifest integrity')
