from dataclasses import dataclass,field
from pathlib import Path
import pytest
from engine.native_checkpoint import render_cached

@dataclass
class Plan:
    shots:list=field(default_factory=list)
    captions:list=field(default_factory=list)

def test_native_checkpoint_tracks_inputs_options_code_and_artifact(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'original')
    implementation=tmp_path/'renderer';implementation.write_bytes(b'version1')
    output=tmp_path/'cut.mp4'
    calls=[]
    def render(v,p,o,**kw):calls.append(p);o.write_bytes(b'unit-test artifact')
    plan=Plan(captions=['سلام'])
    def run(options=None):return render_cached(render,source,plan,output,
        options=options or {'work_dir':tmp_path,'on_progress':lambda x:None,'cta':'الف'},implementations=[implementation])
    assert not run() and run() and len(calls)==1
    plan.captions=['درود']
    assert not run()
    assert not run({'cta':'ب'})
    source.write_bytes(b'changed original')
    assert not run()
    implementation.write_bytes(b'version2')
    assert not run()
    output.write_bytes(b'changed artifact')
    assert not run()

def test_failed_native_render_cannot_write_success_receipt(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'original')
    output=tmp_path/'cut.mp4'
    def fail(*a,**k):raise RuntimeError('encoding failed')
    with pytest.raises(RuntimeError):
        render_cached(fail,source,Plan(),output,options={},implementations=[])
    assert not output.with_suffix('.native-cache.json').exists()
