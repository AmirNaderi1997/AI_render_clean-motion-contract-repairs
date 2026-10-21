"""Dependency identities for existing per-job generation checkpoints."""
import hashlib
import json
from pathlib import Path


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def media_identity(scene, root: Path, aspect: str, static: bool) -> str:
    fields = {'version':2,'aspect':aspect,'static':static,'duration':scene.duration_s,
        'method':scene.media_method,'engine':scene.motion_engine}
    if scene.media_method == 'upload':
        source=(root/scene.source_asset).resolve()
        if not source.is_relative_to(root.resolve()) or not source.is_file():
            raise ValueError('Scene image must belong to this project')
        digest=hashlib.sha256()
        with source.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):
                digest.update(chunk)
        fields['source_sha256']=digest.hexdigest()
    else:
        fields['prompt']=scene.media_prompt or scene.description
    if scene.motion_engine == 'motion_so':
        fields.update(prompt=scene.media_prompt or scene.description,
            effort=scene.motion_effort,background=scene.motion_background)
    return fingerprint(fields)


def reusable(records: list[dict], identity: str, index: int, *, legacy: bool = False) -> dict | None:
    for row in records:
        if not isinstance(row,dict) or not Path(row.get('file_path','')).is_file():
            continue
        if row.get('fingerprint') == identity or (legacy and not row.get('fingerprint') and row.get('scene_index')==index):
            return {**row,'scene_index':index,'fingerprint':identity,'reused':True}
    return None
