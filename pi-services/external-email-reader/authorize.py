#!/usr/bin/env python3
"""Provision only the separate read-only token used by external-email-reader.

It deliberately writes a distinct MSAL cache and requests Mail.Read only. It
cannot send mail, change mailbox rules, or alter the trusted-contact boundary.
"""
import json
from pathlib import Path
import msal

CLIENT_ID = '57d4abf8-8d48-4f89-a8a8-3dd18ca57c57'
TENANT_ID = 'f3f0da70-6bad-4320-975f-a468b8c565b9'
SCOPES = ['Mail.Read']
TOKEN_FILE = Path.home() / '.openclaw/integrations/microsoft/token-external-microsoft-read.json'


def main():
    cache = msal.SerializableTokenCache()
    if TOKEN_FILE.exists():
        cache.deserialize(TOKEN_FILE.read_text())
    app = msal.PublicClientApplication(
        CLIENT_ID, authority=f'https://login.microsoftonline.com/{TENANT_ID}', token_cache=cache
    )
    accounts = app.get_accounts()
    result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
    if not result or 'access_token' not in result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if 'user_code' not in flow:
            raise RuntimeError(flow.get('error_description', 'Microsoft device authorization could not start'))
        print(flow['message'], flush=True)
        result = app.acquire_token_by_device_flow(flow)
    if 'access_token' not in result:
        raise RuntimeError(result.get('error_description', 'Microsoft device authorization failed'))
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(cache.serialize())
    TOKEN_FILE.chmod(0o600)
    print('External read-only Microsoft authorization complete.', flush=True)


if __name__ == '__main__':
    main()
