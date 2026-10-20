"""Enable existing admin-selected media routes without submitting any media.

Capability verification remains mandatory at execution. This script does not
mark untested models verified, invent IDs, or enable paid retries/fallbacks.
"""
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path
from app.config import settings
from app import lm_store
from brain.lm_gateway import defaults


def configure(apply=False):
    routes=defaults();catalog=lm_store.records('models');changes={}
    for key,row in routes.items():
        capability=row.get('capability')
        if capability not in {'image','video','speech','transcription','music'}:continue
        models=[m for m in row.get('models',[]) if m and not m.startswith('auto') and '#vercel-' not in m]
        if capability=='transcription' and not models:
            models=[m for m,v in catalog.items() if 'scribe' in m.lower() and 'transcription' in v.get('verified',[])]
        changes[key]={**row,'enabled':True,'models':models,
            'endpoint':capability,'max_retries':0,'automatic_fallback':False,'specialized_fallback':False,
            'timeout':max(row.get('timeout',0),{'image':150,'video':300,'speech':200,'transcription':200,'music':200}[capability]),
            'configuration_note':'Enabled by administrator; one paid attempt only. Unverified contracts remain blocked. Local Whisper fallback for unavailable STT.'}
        if capability=='transcription':
            changes[key].update(provider_priority=['elevenlabs_own_vercel','jarvis_elevenlabs','sarovi_elevenlabs','whisper_local'],
                configuration_note='Own ElevenLabs via Vercel first; then registered verified Jarvis/Sarovi ElevenLabs models; local Whisper last. No Scribe IDs currently registered for gateway fallbacks.')
    if apply:
        folder=Path(settings.JOBS_DIR)/'ai_gateway'/'backups';folder.mkdir(parents=True,exist_ok=True)
        backup=folder/('media_routes_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json')
        backup.write_text(json.dumps({k:routes[k] for k in changes},ensure_ascii=False))
        lm_store.save('routes',changes)
        saved=lm_store.records('settings').get('direct',{})
        lm_store.patch('settings','direct',{**saved,'stt':{'enabled':True,'model':'small','improve_low_quality':True}})
    return {k:{'enabled':v['enabled'],'models':v['models'],'endpoint':v['endpoint']} for k,v in changes.items()}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    print(json.dumps(configure(args.apply),ensure_ascii=False,indent=2))
