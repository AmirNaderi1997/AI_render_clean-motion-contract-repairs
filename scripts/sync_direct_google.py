"""Owner-authorized Google-only credential sync. Secrets never reach stdout."""
import json
import shlex
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from brain import lm_direct

remote = r'''
const {createRequire} = await import('node:module');
const require = createRequire('/app/server/dist/db/index.js');
const Database = require('better-sqlite3');
const crypto = await import('node:crypto');
const db = new Database('/app/server/data/freeapi.db', {readonly:true});
const row = db.prepare("SELECT encrypted_key,iv,auth_tag FROM api_keys WHERE platform='google' AND enabled=1 AND status='healthy' ORDER BY id DESC LIMIT 1").get();
if (!row || !/^[a-f0-9]{64}$/i.test(process.env.ENCRYPTION_KEY || '')) throw Error('Google credential not available');
const decipher=crypto.createDecipheriv('aes-256-gcm',Buffer.from(process.env.ENCRYPTION_KEY,'hex'),Buffer.from(row.iv,'hex'));
decipher.setAuthTag(Buffer.from(row.auth_tag,'hex'));
const key=decipher.update(row.encrypted_key,'hex','utf8')+decipher.final('utf8');
process.stdout.write(JSON.stringify({key})); db.close();
'''

def main():
    result = subprocess.run(['ssh','-i','/Users/reza/Desktop/rafiei_arvan_ed25519','-p','22222',
        '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
        'root@85.198.49.175',shlex.join(['docker','exec','freellmapi','node','--input-type=module','-e',remote])],
        capture_output=True,timeout=60)
    if result.returncode: raise SystemExit('Secure Google export failed; no local change')
    key=json.loads(result.stdout)['key']
    base='https://generativelanguage.googleapis.com/v1beta'
    response=httpx.get(base+'/models',headers={'x-goog-api-key':key},timeout=25)
    if not response.is_success:
        try:
            error=response.json().get('error', {})
            message=str(error.get('message','')).replace(key,'[REDACTED]')[:250]
        except ValueError:
            message='Non-JSON response'
        raise SystemExit(f'Direct Google catalog HTTP {response.status_code}: {message}; no local change')
    models=[r['name'].removeprefix('models/') for r in response.json().get('models',[])
            if 'generateContent' in r.get('supportedGenerationMethods',[])]
    cfg=lm_direct.config()
    for p in cfg['providers']:
        if p['id']=='gemini':
            preferred='gemini-3.5-flash'
            if preferred not in models: raise SystemExit('Expected configured Gemini model is not in live catalog; no local change')
            p.update(base_url=base,format='gemini',model=preferred,enabled=True,extra_header_name='',prefer_stream=False)
    lm_direct.set_secret('gemini',key)
    lm_direct.save_config(cfg['enabled'],cfg['providers'],cfg['stt'])
    print(json.dumps({'provider':'google direct','catalog_http':response.status_code,'model':'gemini-3.5-flash','secrets_displayed':False}))

if __name__=='__main__': main()
