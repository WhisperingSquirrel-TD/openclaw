#!/usr/bin/env python3
"""Read one exact external Microsoft Graph conversation through a read-only route.
Raw Graph bodies transit only in memory to the broker; this helper cannot write,
search, follow content links, create drafts, or send email.
"""
import argparse, json, re, sys
from html import unescape
from pathlib import Path
from urllib.parse import quote
import requests
GRAPH_BASE='https://graph.microsoft.com/v1.0'; STATE_DIR=Path.home()/'.openclaw'; MAX_MESSAGES=20; MAX_RAW_THREAD_BYTES=4*1024*1024; ACCOUNT='external-microsoft-read'
SELF_ADDRESSES={'tom@stackstoneconsulting.co.uk','tomdean1988@gmail.com','assistant@stackstoneconsulting.co.uk'}
def token(account):
    if account != ACCOUNT: raise RuntimeError('External reader account is fixed to the dedicated read-only account')
    for p in [STATE_DIR/f'integrations/microsoft/token-{account}.json',STATE_DIR/'integrations/microsoft/token-microsoft.json',STATE_DIR/'integrations/microsoft/token.json']:
        if not p.exists(): continue
        data=json.loads(p.read_text()); values=list(data.get('AccessToken',{}).values())
        if values and values[0].get('secret'): return values[0]['secret']
        if data.get('access_token'): return data['access_token']
    raise RuntimeError('Canonical Microsoft Mail.Read token is unavailable')
def graph_get(url,access,params=None):
    response=requests.get(url,params=params,headers={'Authorization':f'Bearer {access}'},timeout=30); response.raise_for_status(); return response.json()
def addresses(value): return [x.get('emailAddress',{}).get('address','').strip().lower() for x in (value or []) if x.get('emailAddress',{}).get('address','').strip()]
def authored_body(content):
    text=str(content or ''); patterns=(r'<div\b[^>]*\bid=["\'](?:x_)?divRplyFwdMsg["\'][^>]*>',r'<div\b[^>]*\bid=["\'](?:x_)?ms-outlook-mobile-body-separator-line["\'][^>]*>',r'<hr\b[^>]*>'); cuts=[m.start() for p in patterns for m in [re.search(p,text,re.I)] if m]
    if cuts: text=text[:min(cuts)]
    text=re.sub(r'<br\s*/?>','\n',text,flags=re.I); text=re.sub(r'</(?:div|p|tr|li|h[1-6])\s*>','\n',text,flags=re.I); text=unescape(re.sub(r'<[^>]+>','',text)); return re.sub(r'[ \t]+',' ',re.sub(r'\n[ \t]*\n+','\n\n',text)).strip()
def normalise_message(message):
    raw=str(message.get('body',{}).get('content','')); sender=(message.get('from',{}).get('emailAddress',{}).get('address') or '').lower(); draft=message.get('isDraft') is True
    return {'message_id':message.get('id'),'conversation_id':message.get('conversationId'),'subject':message.get('subject',''),'sender':sender,'to':addresses(message.get('toRecipients')),'cc':addresses(message.get('ccRecipients')),'received':message.get('receivedDateTime',''),'sent':message.get('sentDateTime',''),'is_draft':draft,'status':'draft' if draft else ('sent' if sender in SELF_ADDRESSES else 'inbound'),'raw_body':raw,'authored_content':authored_body(raw),'body_type':message.get('body',{}).get('contentType','text')}
def main():
    parser=argparse.ArgumentParser();parser.add_argument('message_id');parser.add_argument('--account',default=ACCOUNT);args=parser.parse_args()
    if not args.message_id or len(args.message_id)>512: raise RuntimeError('message id is invalid')
    access=token(args.account); anchor=normalise_message(graph_get(f'{GRAPH_BASE}/me/messages/{quote(args.message_id,safe="")}',access)); cid=anchor.get('conversation_id')
    if not cid: raise RuntimeError('Exact message has no conversation id; complete thread coverage is unavailable')
    response=graph_get(f'{GRAPH_BASE}/me/messages',access,{'$filter':f"conversationId eq '{cid.replace(chr(39),chr(39)*2)}'",'$top':str(MAX_MESSAGES+1)}); values=response.get('value') or []
    if len(values)>MAX_MESSAGES: raise RuntimeError(f'Exact conversation exceeds the bounded {MAX_MESSAGES}-message limit')
    messages=[normalise_message(x) for x in values]
    if not any(x.get('message_id')==anchor.get('message_id') for x in messages): messages.append(anchor)
    messages.sort(key=lambda x:(x.get('received') or x.get('sent') or '',x.get('message_id') or ''))
    if len(messages)>MAX_MESSAGES: raise RuntimeError(f'Exact conversation exceeds the bounded {MAX_MESSAGES}-message limit')
    if any(x.get('conversation_id') not in {None,cid} for x in messages): raise RuntimeError('Exact conversation response contained a message outside the anchor conversation')
    if not messages or not all(x.get('message_id') and x.get('sender') for x in messages): raise RuntimeError('Exact external conversation contains incomplete message identity')
    if sum(len(str(x['raw_body']).encode('utf-8')) for x in messages)>MAX_RAW_THREAD_BYTES: raise RuntimeError(f'Exact conversation raw body exceeds the in-memory {MAX_RAW_THREAD_BYTES}-byte resource ceiling')
    print(json.dumps({'success':True,'conversation_id':cid,'message_count':len(messages),'messages':messages},ensure_ascii=False));return 0
if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:print(json.dumps({'error':str(exc)}),file=sys.stderr);sys.exit(2)
