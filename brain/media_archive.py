"""Local audit artifacts. Never downloads URLs or generates replacement media."""
import base64
import hashlib
import re
from pathlib import Path
from app.config import settings


def root():
    return Path(settings.JOBS_DIR)/'ai_gateway'/'media'


def save(data, mime):
    suffix={'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp',
            'audio/mpeg':'.mp3','audio/wav':'.wav','video/mp4':'.mp4'}.get(mime)
    if not suffix or not data or len(data)>30*1024*1024:
        return None
    key=hashlib.sha256(data).hexdigest()+suffix
    folder=root();folder.mkdir(parents=True,exist_ok=True)
    path=folder/key
    if not path.exists():
        temporary=folder/(key+'.tmp');temporary.write_bytes(data);temporary.replace(path)
    return {'id':key,'mime_type':mime,'size_bytes':len(data),
            'url':'/api/admin/ai/media/'+key}


def images(response):
    artifacts=[]
    for row in response.get('data',[])[:10]:
        if not isinstance(row,dict) or not row.get('b64_json'):continue
        try:
            data=base64.b64decode(row['b64_json'],validate=True)
            mime='image/png' if data.startswith(b'\x89PNG') else 'image/jpeg' if data.startswith(b'\xff\xd8') else 'image/webp' if data[8:12]==b'WEBP' else ''
            artifact=save(data,mime)
            if artifact:artifacts.append(artifact)
        except (ValueError,TypeError):continue
    return artifacts


def resolve(key):
    if not re.fullmatch(r'[a-f0-9]{64}\.(png|jpg|webp|mp3|wav|mp4)',key):raise ValueError('Invalid media ID')
    path=root()/key
    if not path.is_file():raise FileNotFoundError(key)
    return path
