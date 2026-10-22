"""Read-only mapping from rendered shot times to source sentence identities."""
import copy
import re


def source_cuts(plan, start, end):
    if not 0 <= start < end <= plan.duration:
        raise ValueError('بازهٔ حذف خارج از زمان خروجی است.')
    return [{'start':max(start,s.out_start)-s.out_start+s.src_in,
             'end':min(end,s.out_start+s.src_out-s.src_in)-s.out_start+s.src_in}
            for s in plan.shots if max(start,s.out_start)<min(end,s.out_start+s.src_out-s.src_in)]


def subtract_ranges(ranges, cuts):
    for cut in cuts:
        pieces=[]
        for a,b in ranges:
            if cut['end']<=a or cut['start']>=b: pieces.append((a,b)); continue
            if cut['start']-a>.05: pieces.append((a,min(b,cut['start'])))
            if b-cut['end']>.05: pieces.append((max(a,cut['end']),b))
        ranges=pieces
    return ranges


def prepare_transcript(transcript, decisions):
    cuts=decisions.get('source_cuts') or []
    if not cuts: return transcript,decisions
    transcript=copy.deepcopy(transcript);decisions=copy.deepcopy(decisions)
    def removed(w): return any(c['start']<=(w['start']+w['end'])/2<c['end'] for c in cuts)
    original=transcript['words']
    transcript['words']=[w for w in original if not removed(w)]
    for i,s in enumerate(transcript['sentences']):
        inside=[w for w in original if s['start']<=w['start']<s['end']]
        if any(removed(w) for w in inside):
            # Partial ASR false starts must not reappear when rebuilding a cut caption.
            text=' '.join(w.get('w',w.get('text','')) for w in inside if not removed(w)
                          and not re.search(r'(?:--|ـ+)$',w.get('w',w.get('text',''))))
            s['text']=text
            decisions.setdefault('captions',{})[i]=text
    return transcript,decisions


def sentence_ranges(plan, sentences):
    rows=[]
    for index,sentence in enumerate(sentences):
        for shot in plan.shots:
            start=max(float(sentence['start']),shot.src_in)
            end=min(float(sentence['end']),shot.src_out)
            if end-start < .05: continue
            rows.append({'i':index,'output_start':round(shot.out_start+start-shot.src_in,3),
                         'output_end':round(shot.out_start+end-shot.src_in,3)})
    return sorted(rows,key=lambda row:row['output_start'])
