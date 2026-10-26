"""Owner-approved single planning attempt. Never confirms media generation."""
import sys
import ast
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import studio_orchestrator as studio, studio_store as store, jobs
from brain import lm_gateway

CID = '187e8ef29e394efaa307e8584110e8e6'
SOURCE_CID = '558f0acd89a64e2ba377098c31918032'
USER = 'local_dev'

if __name__ == '__main__':
    original = store.run(store.repo.get_conversation(SOURCE_CID, USER))
    target = store.run(store.repo.get_conversation(CID, USER))
    brief = next(m['content'] for m in original['messages'] if m['role'] == 'user')
    jobs.rescan()
    lm_gateway.user_context.set(USER)
    lm_gateway.conversation_context.set(CID)
    studio._assistant(CID, USER, 'بازنویسی سناریو با بریف اصلی و بررسی دوبارهٔ صفحه و تصاویر واقعی محصول آغاز شد. این تلاش فقط برنامه‌ریزی است؛ تصویر، صدا یا ویدیوی تازه تولید نمی‌شود.')
    try:
        # Reuse only the successful, owner-scoped source inspection. The live
        # storefront currently serves an empty shell; do not replace evidence
        # with a guessed summary or a blank screenshot.
        from app.studio_url import PageParser
        from app.studio_flags import conversation_dir
        runs = store._read().get('agent_runs', {})
        evidence = next((operation['result'] for record in reversed(list(runs.values()))
            if record['conversation_id'] == SOURCE_CID and record['user_key'] == USER
            for operation in record.get('data', {}).get('operations', {}).values()
            if operation.get('tool') == 'inspect_url' and operation.get('status') == 'completed'
            and operation.get('result', {}).get('url') in brief), None)
        if not evidence:
            raise ValueError('نتیجهٔ بررسی منبعِ متعلق به همین کاربر موجود نیست؛ محتوای جایگزین ساخته نشد.')
        raw = evidence['content']
        parts = ast.literal_eval(raw) if isinstance(raw, str) and raw.startswith('[') else [raw]
        parser = PageParser()
        for part in parts: parser.feed(str(part))
        images = sorted((conversation_dir(USER,CID)/'url_images').glob('image_*.webp'))
        if not parser.text or not images:
            raise ValueError('متن یا تصاویر ذخیره‌شدهٔ منبع ناقص‌اند.')
        page = {'url':evidence['url'],'title':evidence['title'],'content':parser.text,
                'description':'','structured_products':[],
                'images':[{'file':str(p),'role':'product'} for p in images],
                'extraction':'saved_owner_scoped_tool_result'}
        facts = studio._page_brief(page)
        sources = studio.Sources(pages=[{'url':page['url'],'title':page['title'],
            'text':'\n'.join(parser.text),'page':page,'facts':facts,'images':[str(p) for p in images]}],
            images=[str(p) for p in images])
        studio._assistant(CID,USER,'سایت در بارگذاری جدید محتوای کامل نداد؛ از متن بررسی موفق قبلیِ همین محصول و شش تصویر ذخیره‌شده استفاده می‌کنم. قیمت و موجودی تازه تأیید نشده‌اند و در سناریو اضافه نمی‌شوند.')
        studio._create_motion(CID, USER, 'approved-replan-20261026', brief, [], sources)
        updated = store.run(store.repo.get_conversation(CID, USER))
        if len(updated['projects']) <= len(target['projects']):
            raise ValueError('منابع کافی برای ساخت سناریوی تازه به دست نیامد؛ پروژهٔ جدید ایجاد نشد.')
        latest = updated['projects'][-1]
        # Old pending generation approvals must not compete with the new draft.
        for action in updated['actions']:
            if action['status'] == 'pending' and action['project_id'] != latest['id']:
                store.run(store.repo.update_action(action['id'], 'canceled'))
        print('Planning completed; awaiting user review; no media generation submitted.', flush=True)
    except Exception as exc:
        studio._emit(CID, 'tool.failed', tool='creative_direction', message=str(exc)[:500])
        studio._assistant(CID, USER, 'بازنویسی هنوز به نسخهٔ قابل‌تأیید نرسید. تولید مدیا شروع نشد. ' + str(exc)[:350])
        print(type(exc).__name__ + ': ' + str(exc)[:500], flush=True)
        raise SystemExit(1)
