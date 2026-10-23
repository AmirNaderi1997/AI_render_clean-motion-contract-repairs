"""Compile the chosen concept into existing engine inputs, not another prompt.

No network calls, file paths supplied by a model, arbitrary tools, or media
generation here. Invalid direction stops before paid production.
"""
from __future__ import annotations

from .schemas import CreativePlan, CreativeUnavailable


def storyboard_from_plan(plan: CreativePlan, *, prompt: str, language: str, style: str,
                         duration: float, asset_indices: set[int], brief: dict | None = None):
    from brain.storyboard import Scene, Storyboard
    beats = plan.chosen.beats
    if not 3 <= len(beats) <= 10 or not 15 <= duration <= 90:
        raise CreativeUnavailable('برنامهٔ خلاقانه هنوز صحنه‌های اجرایی کافی یا مدت معتبر ندارد.')
    total_weight = sum(b.duration_weight for b in beats)
    frames = round(duration*30)
    lengths = [round(frames*b.duration_weight/total_weight) for b in beats[:-1]]
    lengths.append(frames-sum(lengths))
    scenes = []
    for index, (beat, length) in enumerate(zip(beats, lengths)):
        seconds = length/30
        if seconds < .5 or not beat.title or not beat.visual or len(beat.title)>80:
            raise CreativeUnavailable(f'صحنهٔ {index+1} عنوان، طراحی یا زمان اجرایی معتبر ندارد.')
        if asset_indices and beat.source_asset_index not in asset_indices:
            raise CreativeUnavailable(f'صحنهٔ {index+1} باید تصویر تأییدشدهٔ مرتبط انتخاب کند.')
        if len(beat.narration.split()) > max(3, int(seconds*2)):
            raise CreativeUnavailable(f'نریشن صحنهٔ {index+1} برای زمان آن طولانی است؛ پیش از تولید باید کوتاه شود.')
        if beat.motion_engine=='motion_so':
            from brain.motion_so import configured
            if not configured():
                raise CreativeUnavailable('Motion.so در این سرور فعال نیست؛ برنامه به موتور غیرقابل‌اجرا ارجاع داده است.')
        scenes.append(Scene(index=index,description=f'{beat.role}: {beat.visual}',duration_s=seconds,
            text_overlay=beat.title,narration_text=beat.narration,
            media_method='upload' if asset_indices else 'generate',media_prompt=beat.visual,
            source_asset_index=beat.source_asset_index,estimated_cost=0,
            narrative_role=beat.role,visual_type=beat.visual_type,motion_style=beat.motion,
            motion_engine=beat.motion_engine))
    return Storyboard(prompt=prompt,content_type='reel',language=language,style=style,
        creative_brief=brief or {}, scenes=scenes,total_duration_s=frames/30,
        # Zero is not a price estimate. Studio separately reports unknown cost
        # for generation providers; actual provider cost remains authoritative.
        estimated_total_cost=0, usage={'model':','.join(plan.models),'source':'creative_plan_v2'})


def bind_talking(plan: CreativePlan, decisions: dict, sentences: list[dict]) -> dict:
    """The director's anchored beats override the second writer's graphic choices.

    Cuts/captions retain their existing engine authority. Explicit style stays
    unchanged. Unsupported or dropped sentence references fail before rendering.
    """
    import copy
    result = copy.deepcopy(decisions)
    if plan.style not in {'talking_2','talking_3'}:
        return result
    board = []
    for beat in plan.chosen.beats:
        i = beat.sentence
        if i is None or not 0 <= i < len(sentences):
            raise CreativeUnavailable('صحنهٔ خلاقانه به جملهٔ واقعی ویدیو متصل نیست.')
        if i in result.get('drop',[]):
            raise CreativeUnavailable('برنامهٔ کات، جملهٔ موردنیاز صحنه را حذف کرده است؛ نیاز به بازبینی دارد.')
        if not beat.title:
            raise CreativeUnavailable('صحنهٔ خلاقانه عنوان نهایی ندارد.')
        if beat.visual_type == 'stat' and not any(c.isdigit() for c in sentences[i]['text']):
            raise CreativeUnavailable('نمایش آمار بدون عدد واقعی در گفتار مجاز نیست.')
        board.append({'i':i,'title':beat.title,'visual_type':beat.visual_type,
            'narrative_role':beat.role,'motion_style':beat.motion,'items':beat.items,'why':beat.intent})
    if board:
        result['storyboard']=board
        # B-roll slots are derived from meaningful beats, not inserted to meet a
        # quota. Asset generation remains the engine's existing approved path.
        prior = {b['i']:b for b in result.get('broll',[])}
        result['broll']=[{**prior.get(row['i'],{}),'i':row['i'],
            'visual_type':row['visual_type'],'visual':beat.visual,'label':row['title'],
            'items':row['items'],'media':prior.get(row['i'],{}).get('media','')}
            for row,beat in zip(board,plan.chosen.beats)]
    return result
