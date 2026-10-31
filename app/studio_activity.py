"""Public operational updates only: no prompts, model reasoning or credentials."""
import contextvars
import functools
import threading
import time
import uuid
from contextlib import contextmanager

description = contextvars.ContextVar('studio_activity_description', default=None)
# What this work is about (the title of the page being read, the topic of the request): step labels say it instead of a generic "this part of the edit".
subject = contextvars.ContextVar('studio_activity_subject', default='')
LABELS = {
    'audio_generation': ('narration', 'در حال ساخت صدای گویندگی از متن تأییدشده هستم.'),
    'transcription': ('transcription', 'در حال دریافت متن گفتار و زمان‌بندی کلمه‌ها هستم.'),
    'intent_classification': ('understanding_request', 'در حال تشخیص نوع تدوین و بررسی درخواست شما هستم.'),
    'creative_director': ('creative_direction', 'در حال طراحی مسیر خلاقانه ویدیو هستم.'),
    'creative_critic': ('creative_review', 'دارم ایده‌ها را از نظر ارتباط، ریتم و کیفیت مقایسه می‌کنم.'),
    'creative_motion': ('motion_generation', 'در حال نوشتن و آماده‌سازی موشن صحنه هستم.'),
    'storyboard_generation': ('storyboard', 'دارم سناریو را به صحنه‌های قابل اجرا تبدیل می‌کنم.'),
    'video_understanding': ('visual_analysis', 'در حال بررسی محتوای تصویر هستم.'),
    'visual_qc': ('visual_review', 'در حال ارزیابی کیفیت بصری خروجی هستم.'),
    'translation': ('translation', 'در حال آماده‌سازی ترجمه هستم.'),
    'script_generation': ('script', 'در حال نوشتن سناریو و متن گویندگی هستم.'),
    'hyperframes_design': ('motion_generation', 'در حال طراحی موشن‌گرافیک هستم.'),
    'remotion_design': ('motion_generation', 'در حال طراحی صحنه‌های موشن هستم.'),
}


def phase_message(stage):
    """Describe observed engine state, never invent internal work or completion."""
    stage = str(stage or '').lower()
    for tokens, message in [
        (('render', 'encoding'), 'مرحلهٔ رندر شروع شده؛ موتور در حال ترکیب تصویر، صدا و نوشته‌ها در فایل ویدیو است.'),
        (('voice', 'speech', 'narration', 'tts'), 'متن گویندگی برای ساخت صدا آماده شده؛ منتظر تکمیل مرحلهٔ صدا هستم.'),
        (('transcrib', 'transcript'), 'گفتار ویدیو در حال تبدیل به متن زمان‌بندی‌شده است.'),
        (('motion', 'design'), 'در حال آماده‌سازی طراحی و موشن صحنه‌ها برای تدوین هستم.'),
        (('review', 'quality', 'qc'), 'فایل خروجی به مرحلهٔ بررسی کیفیت رسیده؛ نتیجهٔ واقعی بررسی را گزارش می‌کنم.'),
        (('caption', 'text', 'hook'), 'در حال آماده‌سازی متن‌ها، هوک و زیرنویس‌های ویدیو هستم.'),
        (('asset', 'generat'), 'پروژه در مرحلهٔ آماده‌سازی دارایی‌هاست؛ فایل‌های آماده برای ادامه استفاده می‌شوند.'),
    ]:
        if any(token in stage for token in tokens): return message
    return 'پردازش این بخش از پروژه شروع شده؛ نتیجهٔ مرحله را همین‌جا گزارش می‌کنم.'


@contextmanager
def describe(stage, message):
    from app.studio_cancel import checkpoint
    checkpoint()
    token = description.set((stage, message))
    try:
        yield
    finally:
        description.reset(token)


def report(conversation_id, kind, **data):
    try:
        from app.studio_orchestrator import _emit
        _emit(conversation_id, kind, **data)
    except Exception:
        # A progress-channel outage must not fail the user's editing operation.
        import logging
        logging.getLogger(__name__).warning('Studio activity update unavailable', exc_info=True)


def observe_request(function):
    @functools.wraps(function)
    def wrapped(route, *args, **kwargs):
        from app.studio_cancel import checkpoint
        checkpoint()
        from brain.lm_gateway import conversation_context
        cid = conversation_context.get()
        if not cid or kwargs.get('probe'):
            return function(route, *args, **kwargs)
        stage, message = description.get() or LABELS.get(route, (route, 'در حال پردازش این بخش از تدوین هستم.'))
        topic = subject.get()
        if topic:
            message = f'{message} (موضوع: «{topic}»)'
        stopped = threading.Event()
        started = time.monotonic()
        activity_id = uuid.uuid4().hex
        data = dict(tool=stage, stage=stage, activity_id=activity_id, message=message, thinking=True)
        report(cid, 'tool.started', **data)
        # The activity step already says what is being done; chat narration is reserved for results (see the orchestrator).
        def waiting():
            while not stopped.wait(15):
                elapsed = int(time.monotonic() - started)
                report(cid, 'tool.progress', **{**data, 'elapsed_seconds': elapsed,
                       'message': f'در انتظار پاسخ سرویس هوش مصنوعی · {elapsed} ثانیه'})
        worker = threading.Thread(target=waiting, daemon=True, name='studio-ai-status')
        worker.start()
        try:
            result = function(route, *args, **kwargs)
            checkpoint()
        except Exception:
            stopped.set()
            worker.join(timeout=1)
            report(cid, 'tool.completed', tool=stage, stage=stage, activity_id=activity_id, thinking=False,
                   message='این تلاش پاسخ قابل استفاده نداد؛ نتیجه به مسیر مدیریت خطا تحویل شد.')
            raise
        else:
            stopped.set()
            worker.join(timeout=1)
            report(cid, 'tool.completed', tool=stage, stage=stage, activity_id=activity_id, thinking=False,
                   message='پاسخ این مرحله دریافت شد؛ اکنون اعتبارسنجی و ادامهٔ پردازش انجام می‌شود.')
            return result
        finally:
            stopped.set()
            worker.join(timeout=1)
    return wrapped
