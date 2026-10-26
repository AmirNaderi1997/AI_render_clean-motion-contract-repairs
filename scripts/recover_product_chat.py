"""One-off owner-approved recovery of the deleted local PuBang project.

Only reconstructs the storyboard visible in the surviving Studio page. Does not
claim to restore deleted assets, checkpoints, approvals, or original run history.
No provider requests or media generation. Refuses to overwrite an existing chat.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import studio_store as store
from app import jobs
from brain.storyboard import Scene, Storyboard

CID = '187e8ef29e394efaa307e8584110e8e6'
OWNER = 'local_dev'
URL = 'https://store.rafiei.co/store/reza/product/669aff79-29ee-49f9-a1bb-835c2e83790d'
BRIEF = '''بازسازی از متن باقی‌ماندهٔ صفحه؛ نه تاریخچهٔ اصلی بازیابی‌شده.
تبلیغ انگشتر PuBang برای Instagram Reels / TikTok / YouTube Shorts، عمودی ۹:۱۶،
۱۰۸۰×۱۹۲۰، ۲۵ تا ۳۵ ثانیه، با نریشن محاوره‌ای فارسی، هوک کنجکاوی‌برانگیز،
تدوین سریع و حرفه‌ای و CTA صفحه محصول. هدف کیفیت Premium UGC + Cinematic Product Commercial است.
ظاهر و نسبت‌ها و رنگ‌های واقعی محصول حفظ شود. قیمت، تخفیف، نظر مشتری، ویژگی،
تضمین، واکنش مشتری و نتیجهٔ ساختگی اضافه نشود. تصویر اصلی محصول در اولویت است.
صدا، زیرنویس خوانای فارسی، زوم‌ها، ترنزیشن و موشن باید در خدمت روایت باشند.
ویدیو کامل خواسته شده، نه فقط سناریو. مشخصات نقل‌شده از متن چت قبلی:
نقره استرلینگ ۹۲۵، یاقوت تراش کله‌قندی، الماس پرکربن، طراحی مجلسی،
کاربرد سالگرد، هدیه و رویداد خاص. این مشخصات در بازیابی دوباره بررسی نشده‌اند.
منبع محصول: ''' + URL

# Exact visible seven-scene draft; no substitution with a new generic template.
ROWS = [
 (3.1, 'کله‌قندی؟ برای یاقوت؟', 'کله‌قندی؟', 'کادر عمودی مشکی؛ دو واژه «کله‌قندی؟» و «یاقوت؟» جدا از هم، بدون لوگو و بدون تصویر محصول', 'دو واژه سؤال را می‌سازند و نبودن تصویر، مخاطب را برای پاسخ نگه می‌دارد', 'motion_graphic'),
 (5.8, 'وقتی برای یه شب خاص انگشتر می‌خوای، جزئیات مهم می‌شن.', 'انتخاب خاص', 'یک خط باریک نور روی زمینه مشکی حرکت می‌کند و کنار آن واژه‌های «شب خاص» و «جزئیات» ظاهر می‌شوند', 'تنش انتخاب را به جزئیات وصل می‌کند، بدون ساختن موقعیت یا محصولی حدسی', 'concept'),
 (4.5, 'این یکی، انگشتر لوکس نقره PuBang ـه.', 'PuBang', 'نام لاتین PuBang در مرکز کادر؛ زیر آن عبارت فارسی «انگشتر لوکس نقره» با خط نقره‌ای باریک', 'محصول را معرفی می‌کند، بدون بازسازی ظاهر یا تغییر برندینگ آن', 'motion_graphic'),
 (5.8, 'یاقوتش تراش کله‌قندی داره؛ کنارش هم الماس پرکربنه.', 'دو جزئیات', 'دو ناحیه تایپوگرافیک در قاب؛ «یاقوت / تراش کله‌قندی» در بالا و «الماس پرکربن» در پایین، با خطوط راهنمای نقره‌ای', 'جزئیات تأییدشده را روشن می‌کند، بدون نمایش حدسی شکل یا درخشش سنگ', 'motion_graphic'),
 (3.9, 'جنسش نقره استرلینگ ۹۲۵ عیاره.', '۹۲۵ عیار', 'عدد بزرگ «۹۲۵» در مرکز؛ عبارت «نقره استرلینگ» زیر آن، روی بافت تیره و ساده', 'جنس محصول را مستقیم و خوانا نشان می‌دهد، بدون نسبت‌دادن راحتی یا دوام تأییدنشده', 'motion_graphic'),
 (5.4, 'برای مهمونی کوکتل، سالگرد، یا یه هدیه خاص.', 'لحظه مهم', 'سه برچسب کوتاه «مهمانی کوکتل»، «سالگرد» و «هدیه» یکی‌یکی روی یک محور عمودی روشن می‌شوند', 'کاربردهای تأییدشده را سریع نشان می‌دهد، بدون صحنه‌سازی یا واکنش ساختگی', 'motion_graphic'),
 (6.5, 'برای کسی که هنوز می‌پرسه «کله‌قندی؟»، صفحه محصول رو ببین.', 'جزئیات محصول', 'واژه «کله‌قندی؟» دوباره در مرکز کادر دیده می‌شود؛ زیر آن فلش باریک رو به پایین و عبارت «صفحه محصول» قرار می‌گیرد', 'پایان، تصویر و سؤال شروع را به مقصد دیدن محصول وصل می‌کند', 'concept'),
]


async def main():
    if store.DB_AVAILABLE:
        raise SystemExit('Local JSON recovery only; production is never modified')
    data = store._read()
    if CID in data['conversations']:
        raise SystemExit('Conversation exists; refusing to overwrite')
    stamp = store.iso(store.now())
    data['conversations'][CID] = dict(id=CID, user_key=OWNER,
        title='تبلیغ انگشتر PuBang — پروژهٔ بازسازی‌شده', language='fa',
        status_voice_enabled=False, state={'agent_mode':'medium','recovered_from_visible_page':True},
        created_at=stamp, updated_at=stamp)
    store._write(data)
    repo = store.Repository()
    await repo.add_message(CID, OWNER, 'user', BRIEF, agent_mode='medium')
    board = Storyboard(prompt=BRIEF, content_type='reel', language='fa', style='rafiei_reel',
        creative_brief={'goal':'تبلیغ محصول','avoid':'ادعای تأییدنشده'},
        scenes=[Scene(index=i+1, description=description, duration_s=duration,
            narration_text=narration, text_overlay=overlay, media_prompt=description,
            script_line=narration, why_visual=why, visual_type=visual)
            for i,(duration,narration,overlay,description,why,visual) in enumerate(ROWS)],
        total_duration_s=sum(row[0] for row in ROWS))
    # The surviving durations sum to 35 seconds. Assets are explicitly missing.
    job = jobs.create_job(user_id=OWNER)
    (job.dir/'generated').mkdir(exist_ok=True)
    (job.dir/'storyboard.json').write_text(json.dumps(board.to_dict(),ensure_ascii=False,indent=2))
    (job.dir/'generation_status.json').write_text(json.dumps(dict(state='pending',scenes_done=0,
        scenes_total=7,cost_so_far=None,cost_status='not_started',content_type='reel',provider='lm_gateway')))
    project = await repo.create_project(CID, OWNER, 'motion', 'انگشتر PuBang',
        {'request':BRIEF,'storyboard':board.to_dict(),'provider':'lm_gateway','auto_render':True,
         'last_observed':{},'recovered_from_visible_page':True,'missing_original_assets':True},job.id)
    action = await repo.create_action(CID,project['id'],'generate_motion_video',
        {'job_id':job.id,'provider':'lm_gateway'},'recovery-'+CID,None)
    await repo.update_project(project['id'],OWNER,status='awaiting_confirmation')
    await repo.add_message(CID,OWNER,'assistant',
        'چت و سناریوی ۷ صحنه‌ای از متن صفحه بازسازی شدند. فایل‌های تصویری، صوتی و تاریخچهٔ اجرای حذف‌شده بازیابی نشده‌اند. '
        'این نسخه بازسازی است؛ متن مشخصات محصول از چت قبلی نقل شده و بررسی دوباره نشده است. '
        'پیش از تولید مجدد، سناریو و تنظیمات مدل را بررسی کنید. تولید مجدد اعتبار مصرف می‌کند.')
    await repo.emit(CID,'storyboard.ready',{'project_id':project['id'],'action_id':action['id'],
        'storyboard':board.to_dict(),'message':'سناریوی بازسازی‌شده آمادهٔ بررسی است'})
    # Independent recovery copy outside the runtime directory that was deleted.
    safe = Path(__file__).resolve().parents[1]/'recovery'/CID
    safe.mkdir(parents=True,exist_ok=True,mode=0o700)
    (safe/'storyboard.json').write_text(json.dumps(board.to_dict(),ensure_ascii=False,indent=2))
    (safe/'studio.json').write_text(json.dumps(store._read(),ensure_ascii=False,indent=2))
    print(json.dumps({'conversation':CID,'project':project['id'],'job':job.id,
        'action':action['id'],'recovery_copy':str(safe)}))


if __name__ == '__main__':
    asyncio.run(main())
