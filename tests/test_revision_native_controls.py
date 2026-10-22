from types import SimpleNamespace
from PIL import Image
from creative.revise import RevisionOp, apply_to_talking
from app.talking_reel import _apply_timeline_choices, _clean_render_settings
from engine.revision_timing import sentence_ranges, source_cuts, prepare_transcript, subtract_ranges
from engine.talking_styles.talking_1 import vignette_png


def test_native_controls_are_available_without_disabling_all_moments():
    state={'style':'talking_1','render_settings':{'zoom':{'amount':100,'base_scale':100,'close_scale':140}}}
    result=apply_to_talking(state,[RevisionOp(op='set_render',settings={
        'first_key_moment_enabled':False,'base_scale':110,'close_scale':154,'bottom_shade':25}),
        RevisionOp(op='remove_sentence',sentence=2)],4)
    assert not result.unsupported
    settings=_clean_render_settings(result.changes['render_settings'])
    assert settings['zoom']['base_scale']==110 and settings['zoom']['amount']==100
    assert settings['first_key_moment_enabled'] is False
    assert settings['key_moments_enabled'] is True
    decisions=_apply_timeline_choices({'cold_open':{'i':0},'drop':[],
        'notes':[{'i':2,'text':'x'},{'i':3,'text':'y'}],'bw':[2,3]},'talking_1',settings)
    assert decisions['cold_open'] is None and decisions['drop']==[2]
    assert decisions['bw']==[3] and decisions['notes']==[{'i':3,'text':'y'}]


def test_output_timestamp_mapping_keeps_teaser_and_cut_offsets():
    plan=SimpleNamespace(shots=[SimpleNamespace(src_in=50,src_out=53,out_start=0),
        SimpleNamespace(src_in=0,src_out=10,out_start=3),
        SimpleNamespace(src_in=50,src_out=60,out_start=13)])
    rows=sentence_ranges(plan,[{'start':50,'end':53}])
    assert rows==[{'i':0,'output_start':0,'output_end':3},
                  {'i':0,'output_start':13,'output_end':16}]


def test_lower_shade_is_below_text_and_does_not_darken_upper_frame(tmp_path):
    a=vignette_png(tmp_path/'a.png')
    b=vignette_png(tmp_path/'b.png',.25)
    with Image.open(a) as old, Image.open(b) as new:
        assert old.getpixel((540,400))==new.getpixel((540,400))
        assert new.getpixel((540,1850))[3]>old.getpixel((540,1850))[3]


def test_partial_cut_preserves_rest_of_sentence_and_original_transcript():
    t={'words':[{'start':0,'end':1,'w':'اول'},{'start':1,'end':2,'w':'تکرار'},{'start':2,'end':3,'w':'ادامه'}],
       'sentences':[{'start':0,'end':3,'text':'اول تکرار ادامه'}]}
    decisions={'source_cuts':[{'start':1,'end':2}],'captions':{0:'اول تکرار ادامه'}}
    edited,d=prepare_transcript(t,decisions)
    assert d['captions'][0]=='اول ادامه' and len(t['words'])==3
    assert len(edited['words'])==2
    assert subtract_ranges([(0,3)],d['source_cuts'])==[(0,1),(2,3)]
    from engine.talking_styles.talking_1 import plan_reel
    plan_cut=plan_reel(edited,d,[],3)
    assert all(shot.src_out<=1 or shot.src_in>=2 for shot in plan_cut.shots)
    assert abs(plan_cut.duration-2)<.01
    assert all('تکرار' not in cue['text'] for cue in plan_cut.captions)
    plan=SimpleNamespace(duration=3,shots=[SimpleNamespace(src_in=10,src_out=13,out_start=0)])
    assert source_cuts(plan,1,2)==[{'start':11,'end':12}]


def test_shared_plan_keeps_main_source_cuts_in_readonly_timeline(tmp_path, monkeypatch):
    import json
    from app import talking_reel
    transcript={'duration':3,'words':[{'start':0,'end':1,'w':'اول'},
        {'start':1,'end':2,'w':'تکرار'},{'start':2,'end':3,'w':'ادامه'}],
        'sentences':[{'start':0,'end':3,'text':'اول تکرار ادامه'}]}
    (tmp_path/'transcript.json').write_text(json.dumps(transcript))
    monkeypatch.setattr(talking_reel,'load',lambda _: {'style':'talking_1',
        'decisions':{'captions':{'0':'اول تکرار ادامه'},'drop':[]},
        'render_settings':{'source_cuts':[{'start':1,'end':2}]}})
    monkeypatch.setattr(talking_reel,'transcript_for',lambda *a: (_ for _ in ()).throw(AssertionError('no ASR')))
    planned=talking_reel.plan_render(tmp_path,tmp_path/'source.mp4',prepare_media=False)
    assert planned.plan.duration == 2
    assert all(s.src_out<=1 or s.src_in>=2 for s in planned.plan.shots)
    assert all('تکرار' not in c['text'] for c in planned.plan.captions)
