#!/usr/bin/env python3
"""Publish one existing OpenClaw skill in place to SharePoint.

SharePoint native version history is the only release history. The manifest is
content-addressed: canonical paths, file hashes and bundle hashes only.
"""
from __future__ import annotations
import argparse, importlib.util, json, sys
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).parent))
from skill_library_release import release_record, validate_manifest, sha256

WORKSPACE = Path('/home/tomdean88/.openclaw/workspace')
ROOT = '/skills/openclaw-skill-estate'
SOURCES = {'workspace-skills': WORKSPACE / 'skills', 'openclaw-skills': Path('/home/tomdean88/openclaw/skills')}

def client():
    spec=importlib.util.spec_from_file_location('sp','/home/tomdean88/.openclaw/integrations/microsoft-l1/sharepoint.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); module._load_dotenv()
    class Args: account='assistant'; token_file=None
    token=module.get_access_token(Args()); site,drive=module._resolve_site_and_drive(token)
    return f'https://graph.microsoft.com/v1.0/sites/{site}/drives/{drive}', {'Authorization':f'Bearer token'} if False else {'Authorization':f'Bearer {token}'}

def get(base,h,path):
    r=requests.get(base+f'/root:{path}:/content',headers=h,timeout=90)
    if not r.ok: raise RuntimeError(f'GET {path}: {r.status_code} {r.text[:160]}')
    return r.content,r.headers.get('ETag')

def put(base,h,path,data):
    r=requests.put(base+f'/root:{path}:/content',headers={**h,'Content-Type':'application/octet-stream'},data=data,timeout=90)
    if not r.ok: raise RuntimeError(f'PUT {path}: {r.status_code} {r.text[:160]}')
    return r.json().get('eTag')

def normalize_legacy_manifest(manifest):
    if manifest.get('schema_version') == 2:
        for record in manifest.get('skills', {}).values(): record.pop('version', None)
        manifest['schema_version'] = 3
    validate_manifest(manifest)
    return manifest

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('skill_id', help='e.g. workspace-skills:skill-update'); ap.add_argument('--summary',required=True); ap.add_argument('--dry-run',action='store_true'); args=ap.parse_args()
    source,sep,name=args.skill_id.partition(':')
    if not sep or source not in SOURCES or '/' in name: raise ValueError('invalid skill id')
    local=SOURCES[source]/name
    if not local.is_dir(): raise FileNotFoundError(local)
    base,h=client(); manifest_path=ROOT+'/MANIFEST.json'; baseline_raw,baseline_etag=get(base,h,manifest_path)
    manifest=normalize_legacy_manifest(json.loads(baseline_raw)); record=manifest['skills'].get(args.skill_id)
    if not record: raise RuntimeError('skill absent from canonical manifest; create/release requires reviewed migration')
    if record['canonical_path'] != f'{source}/{name}': raise RuntimeError('manifest canonical path mismatch')
    for entry in record['files']:
        raw,_=get(base,h,ROOT+'/'+record['canonical_path']+'/'+entry['path'])
        if sha256(raw)!=entry['sha256'] or len(raw)!=entry['bytes']: raise RuntimeError('baseline SharePoint content mismatches manifest')
    intended=release_record(record['canonical_path'],local)
    latest_raw,_=get(base,h,manifest_path)
    if sha256(latest_raw)!=sha256(baseline_raw): raise RuntimeError('concurrent manifest change; no write')
    for entry in record['files']:
        raw,_=get(base,h,ROOT+'/'+record['canonical_path']+'/'+entry['path'])
        if sha256(raw)!=entry['sha256'] or len(raw)!=entry['bytes']: raise RuntimeError('concurrent skill file change; no write')
    if args.dry_run:
        print(json.dumps({'skill':args.skill_id,'files':len(intended['files']),'manifest_schema':3,'dry_run':True},indent=2)); return
    for entry in intended['files']:
        put(base,h,ROOT+'/'+intended['canonical_path']+'/'+entry['path'],(local/entry['path']).read_bytes())
    manifest['skills'][args.skill_id]={**intended,'change_summary':args.summary}
    new_raw=json.dumps(manifest,indent=2).encode(); put(base,h,manifest_path,new_raw)
    confirmed_raw,confirmed_etag=get(base,h,manifest_path)
    if confirmed_raw!=new_raw: raise RuntimeError('manifest post-write mismatch')
    confirmed=json.loads(confirmed_raw);validate_manifest(confirmed)
    if confirmed['skills'][args.skill_id]!=manifest['skills'][args.skill_id]: raise RuntimeError('manifest skill record mismatch')
    for entry in intended['files']:
        raw,_=get(base,h,ROOT+'/'+intended['canonical_path']+'/'+entry['path'])
        if sha256(raw)!=entry['sha256'] or len(raw)!=entry['bytes']: raise RuntimeError('file post-write mismatch')
    print(json.dumps({'skill':args.skill_id,'files':len(intended['files']),'manifest_etag':confirmed_etag,'verified':True},indent=2))
if __name__=='__main__': main()
