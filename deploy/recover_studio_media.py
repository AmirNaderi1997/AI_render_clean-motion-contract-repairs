"""Recover only existing checkpoint assets. No provider calls, no render calls.
Usage: python -m deploy.recover_studio_media CONVERSATION_ID JOB_ID
"""
import asyncio
import json
import sys
from pathlib import Path
from app.studio_store import repo
from app.database import AsyncSessionLocal
from app.models import StudioConversation
from app.config import settings
from brain.media_archive import save
from app import lm_store


async def recover(cid,jid):
    async with AsyncSessionLocal() as db:
        conversation=await db.get(StudioConversation,cid)
        if not conversation:raise ValueError('Conversation not found')
        user=conversation.user_key
    projects=(await repo.get_conversation(cid,user))['projects']
    if not any(p.get('external_ref')==jid for p in projects):raise ValueError('Job is not linked to conversation')
    folder=Path(settings.JOBS_DIR)/jid
    checkpoint=json.loads((folder/'generated/generation_checkpoint.json').read_text())
    marker=folder/'generated/.media-recovery-linked'
    if marker.exists():print('Already recovered');return
    ids=[];artifacts=[]
    for media in checkpoint.get('media',[]):
        for filename in (media.get('metadata',{}).get('still_path'),media.get('file_path')):
            if not filename:continue
            path=Path(filename).resolve()
            if not path.is_relative_to(folder.resolve()) or not path.is_file():continue
            kind='image' if path.suffix=='.png' else 'video'
            mime='image/png' if kind=='image' else 'video/mp4'
            item=await repo.create_attachment(cid,user,kind=kind,filename=path.name,path=str(path),
                mime_type=mime,size_bytes=path.stat().st_size,metadata={'recovered':True,'job_id':jid,'scene_index':media['scene_index']})
            ids.append(item['id'])
            artifact=save(path.read_bytes(),mime)
            if artifact:artifacts.append(artifact)
    await repo.add_message(cid,user,'assistant',
        'سه تصویر آماده و سه کلیپ موشن موجود بازیابی شدند و اینجا قابل مشاهده‌اند. این فایل‌ها در چک‌پوینت ذخیره‌اند و برای ادامه دوباره تولید نمی‌شوند. برای سایر درخواست‌های موفق، فایل پاسخ در ذخیره‌سازی فعلی موجود نیست؛ هیچ تولید مجددی انجام نشد.',ids)
    marker.touch()
    # Recovered asset inventory is a local audit event, not a fabricated provider success.
    from datetime import datetime,timezone
    await lm_store._log({'id':'recovered-'+jid,'timestamp':datetime.now(timezone.utc).isoformat(),
        'job_id':jid,'conversation_id':cid,'user_id':user,'route':'media_recovery',
        'status':'recovered','requested_model':'existing-assets','actual_model':None,'media':artifacts,
        'request_message':'Recover persisted checkpoint assets; no provider request.',
        'response_message':f'{len(artifacts)} existing assets attached; no generation performed.',
        'latency_ms':0})
    print({'recovered_attachments':len(ids)})


if __name__=='__main__':asyncio.run(recover(*sys.argv[1:]))
