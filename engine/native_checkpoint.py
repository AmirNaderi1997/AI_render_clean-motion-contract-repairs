"""Content-bound native-cut checkpoint for graphics-only continuations."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path


def _stamp(path):
    path=Path(path)
    stat=path.stat()
    return [str(path.resolve()),stat.st_size,stat.st_mtime_ns]


def native_key(source,plan,options,implementations):
    options={k:v for k,v in options.items() if k not in {'work_dir','on_progress'}}
    files=[Path(source)]
    files += [Path(options[k]) for k in ('music','logo_path','overlay') if options.get(k)]
    files += [Path(s.picture) for s in plan.shots if getattr(s,'picture',None)]
    value={'version':1,'inputs':[_stamp(p) for p in files], 'plan':asdict(plan), 'options':options,
        'implementations':{str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in implementations}}
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def save_checkpoint(output,key):
    output=Path(output)
    assert output.is_file() and output.stat().st_size>0
    receipt=output.with_suffix('.native-cache.json')
    temporary=receipt.with_suffix('.tmp')
    temporary.write_text(json.dumps({'key':key,'artifact':_stamp(output)}))
    temporary.replace(receipt)


def render_cached(render,source,plan,output,*,options,implementations):
    """Return True only for the exact prior artifact and unchanged inputs/code."""
    output=Path(output)
    key=native_key(source,plan,options,implementations)
    try:
        saved=json.loads(output.with_suffix('.native-cache.json').read_text())
        if saved['key']==key and saved['artifact']==_stamp(output) and output.stat().st_size>0:
            return True
    except (OSError,ValueError,KeyError):
        pass
    render(source,plan,output,**options)
    save_checkpoint(output,key)
    return False
