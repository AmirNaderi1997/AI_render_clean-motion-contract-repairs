"""Owner-authorized, read-only SSH export of EditorGPT AI configuration.

Run from the destination backend directory with its Python environment.
Secrets travel over verified SSH into memory, never command arguments or stdout.
No requests to AI providers and no remote writes are performed.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

EXPORT = '''
import json
from app import lm_store
from app.config import settings
from brain import lm_direct
cfg = lm_direct.config()
keys = {p['id']: lm_direct.key_for(p['id']) for p in cfg['providers']}
headers = {p['id']: lm_direct.header_value_for(p['id']) for p in cfg['providers']}
print(json.dumps({'models': lm_store.records('models'), 'routes': lm_store.records('routes'),
 'direct': cfg, 'keys': keys, 'headers': headers,
 'settings': {k:v for k,v in lm_store.records('settings').items() if k in ('global','discovery')}}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identity', required=True)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=22222)
    parser.add_argument('--container', default='ai-render-app-1')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not (Path.cwd() / 'app/lm_store.py').is_file():
        raise SystemExit('Run from the destination EditorGPT backend directory')
    sys.path.insert(0, str(Path.cwd()))
    from app import lm_store
    from app.config import settings
    from brain import lm_direct
    command = ['ssh', '-i', args.identity, '-p', str(args.port), '-o', 'IdentitiesOnly=yes',
               '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
               args.host, shlex.join(['docker', 'exec', args.container, 'python', '-c', EXPORT])]
    result = subprocess.run(command, capture_output=True, timeout=90, check=False)
    if result.returncode:
        raise SystemExit('Remote read failed; no configuration was imported')
    try:
        source = json.loads(result.stdout)
        assert isinstance(source['models'], dict) and source['models']
        assert isinstance(source['routes'], dict) and source['routes']
        assert all(v.get('id') == k for k, v in source['models'].items())
        cfg = source['direct']
        assert isinstance(cfg['providers'], list)
        assert all(p['id'] in lm_direct.PROVIDERS for p in cfg['providers'])
        for p in cfg['providers']:
            lm_direct.validate_base_url(p['base_url'])
    except (ValueError, KeyError, TypeError, AssertionError):
        raise SystemExit('Source validation failed; no configuration was imported') from None
    report = {'models': len(source['models']), 'routes': len(source['routes']),
              'direct_keys_available': [k for k,v in source['keys'].items() if v],
              'applied': False}
    if not args.apply:
        print(json.dumps(report))
        return
    root = Path(settings.JOBS_DIR) / 'ai_gateway'
    backups = root / 'backups'
    backups.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = Path(tempfile.mkdtemp(prefix='before-online-sync-', dir=backups))
    for src, name in ((root/'state.json', 'state.json'), (root/'direct_keys.json', 'direct_keys.json')):
        if src.is_file():
            shutil.copy2(src, backup/name)
            os.chmod(backup/name, 0o600)
    # Existing local-only models, routes, logs and settings are retained. Online
    # entries win for matching IDs; no user/project tables are touched.
    lm_store.save('models', source['models'])
    lm_store.save('routes', source['routes'])
    lm_store.save('settings', source['settings'])
    lm_direct.save_config(cfg['enabled'], cfg['providers'], cfg.get('stt'))
    for provider, key in source['keys'].items():
        if key: lm_direct.set_secret(provider, key)
    for provider, header in source['headers'].items():
        if header: lm_direct.set_secret(provider+':header', header)
    actual_models, actual_routes = lm_store.records('models'), lm_store.records('routes')
    report.update(applied=True, backup=str(backup),
                  models_match=all(actual_models.get(k)==v for k,v in source['models'].items()),
                  routes_match=all(actual_routes.get(k)==v for k,v in source['routes'].items()))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
