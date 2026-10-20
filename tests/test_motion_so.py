import json
import shutil
import subprocess
from types import SimpleNamespace
import pytest
from brain import motion_so as motion
from brain.storyboard import Scene,Storyboard


@pytest.fixture
def scene():return Scene(index=0,description='Animated comparison chart',duration_s=1,motion_engine='motion_so')


@pytest.fixture(autouse=True)
def no_live_mcp(monkeypatch):
    from brain.motion_messages import MessageReader
    monkeypatch.setattr(MessageReader,'pull',lambda *a:None)
    monkeypatch.setattr('brain.motion_messages.start_reader',lambda *a:None)
    monkeypatch.setattr(motion,'secret',lambda:'test-key')


def test_schema_and_security(scene):
    assert Storyboard.from_dict({'scenes':[scene.to_dict()]}).scenes[0].motion_engine=='motion_so'
    for url in ['http://storage.googleapis.com/x','https://127.0.0.1/x','https://storage.googleapis.com.evil.org/x','https://user@storage.googleapis.com/x']:
        with pytest.raises(ValueError):motion._storage_url(url)
    with pytest.raises(ValueError):Scene(index=0,description='x',duration_s=1,motion_engine='shell')


def test_ambiguous_post_never_submits_again(monkeypatch,tmp_path,scene):
    monkeypatch.setattr(motion,'configured',lambda:True)
    calls=[]
    def call(method,path,body=None):
        calls.append(method);raise TimeoutError('simulated')
    monkeypatch.setattr(motion,'call',call)
    with pytest.raises(TimeoutError):motion.generate_scene(scene,tmp_path,'9:16')
    with pytest.raises(ValueError,match='uncertain'):motion.generate_scene(scene,tmp_path,'9:16')
    assert calls==['POST']


def test_poll_failure_reuses_remote_job(monkeypatch,tmp_path,scene):
    monkeypatch.setattr(motion,'configured',lambda:True)
    calls=[]
    def call(method,path,body=None):
        calls.append((method,path))
        if method=='POST':return {'job_id':'existing-job','status':'queued'}
        raise TimeoutError('simulated polling failure')
    monkeypatch.setattr(motion,'call',call)
    for _ in range(2):
        with pytest.raises(TimeoutError):motion.generate_scene(scene,tmp_path,'9:16')
    assert [m for m,p in calls]==['POST','GET','GET']


def test_real_local_normalization_and_cache_without_provider(monkeypatch,tmp_path,scene):
    if not shutil.which('ffmpeg'):pytest.skip('ffmpeg unavailable')
    fixture=tmp_path/'fixture.mp4'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=c=navy:s=160x90:r=30',
        '-f','lavfi','-i','sine=frequency=440','-t','1','-c:v','libx264','-c:a','aac',str(fixture)],check=True)
    monkeypatch.setattr(motion,'configured',lambda:True)
    calls=[]
    def call(method,path,body=None):
        calls.append(method)
        return {'job_id':'saved-job','status':'queued'} if method=='POST' else {
            'status':'completed','output':{'status':'completed','download_url':'https://storage.googleapis.com/test/output'}}
    monkeypatch.setattr(motion,'call',call)
    monkeypatch.setattr(motion,'_download',lambda url,target:shutil.copy2(fixture,target))
    first=motion.generate_scene(scene,tmp_path,'9:16')
    second=motion.generate_scene(scene,tmp_path,'9:16')
    from engine.probe import has_audio,video_dimensions,probe_duration
    assert video_dimensions(__import__('pathlib').Path(first.file_path))==(1080,1920)
    assert not has_audio(__import__('pathlib').Path(first.file_path))
    assert abs(probe_duration(__import__('pathlib').Path(first.file_path))-1)<.1
    assert first.file_path==second.file_path and calls==['POST','GET']


def test_confirmation_before_generation(monkeypatch,tmp_path):
    from app.routers import motion_so as api
    monkeypatch.setattr(api,'get_job_for_request',lambda *a:SimpleNamespace(id='owned',dir=tmp_path))
    monkeypatch.setattr(motion,'configured',lambda:pytest.fail('No provider access without approval'))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:api.create_scene('owned',api.SceneRequest(prompt='chart'),None)
    assert error.value.status_code==409


@pytest.mark.parametrize('shot_count',[1,24])
def test_native_talking_two_panel_real_ffmpeg(monkeypatch,tmp_path,shot_count):
    from engine.talking_styles import talking_2 as split
    from engine.render_ass import ass_burner_ffmpeg
    if not ass_burner_ffmpeg():pytest.skip('libass ffmpeg unavailable')
    monkeypatch.setattr(split,'W',320);monkeypatch.setattr(split,'H',568);monkeypatch.setattr(split,'SPLIT_Y',284)
    monkeypatch.setattr(split,'render_outro',lambda *a,**k:(None,0))
    speaker=tmp_path/'speaker.mp4';panel=tmp_path/'panel.mp4';out=tmp_path/'mixed.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=320x568:r=30',
        '-f','lavfi','-i','sine=frequency=330','-t','1','-c:v','libx264','-c:a','aac',str(speaker)],check=True)
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=green:s=320x284:r=30',
        '-t','1','-c:v','libx264',str(panel)],check=True)
    plan=split.ReelPlan(shots=[split.Shot(0,1,split=True,picture=str(panel),slot=k) for k in range(shot_count)],duration=shot_count)
    split.render_plain(speaker,plan,out,work_dir=tmp_path/'work',render_settings={'grade':{'vignette':0}})
    from engine.probe import has_audio,probe_duration
    assert has_audio(out) and abs(probe_duration(out)-shot_count)<.1
    from PIL import Image
    import io
    frame=subprocess.run(['ffmpeg','-v','error','-ss','0.3','-i',str(out),'-frames:v','1','-f','image2pipe','-c:v','png','-'],check=True,capture_output=True).stdout
    image=Image.open(io.BytesIO(frame)).convert('RGB')
    top=image.getpixel((160,140));bottom=image.getpixel((160,420))
    assert top[1]>top[2] and bottom[2]>bottom[1]


def test_native_talking_one_sequential_cache_and_audio(monkeypatch,tmp_path):
    from engine.talking_styles import talking_1 as engine
    from engine.render_ass import ass_burner_ffmpeg
    from engine.probe import has_audio,probe_duration
    if not ass_burner_ffmpeg():pytest.skip('libass ffmpeg unavailable')
    monkeypatch.setattr(engine,'W',320);monkeypatch.setattr(engine,'H',568)
    monkeypatch.setattr(engine,'render_outro',lambda *a,**k:(None,0))
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=320x568:r=30',
        '-f','lavfi','-i','sine=frequency=330','-t','1','-c:v','libx264','-c:a','aac',str(source)],check=True)
    plan=engine.ReelPlan(shots=[engine.Shot(0,1),engine.Shot(0,1,push=True)],duration=2)
    kwargs=dict(work_dir=tmp_path/'work',hook='',highlight=[],name='',title='',render_settings={'grade':{'vignette':0}})
    engine.render_plain(source,plan,tmp_path/'first.mp4',**kwargs)
    before={p.name:p.stat().st_mtime_ns for p in (tmp_path/'work'/'shot_cache').glob('*.mkv')}
    engine.render_plain(source,plan,tmp_path/'second.mp4',**kwargs)
    after={p.name:p.stat().st_mtime_ns for p in (tmp_path/'work'/'shot_cache').glob('*.mkv')}
    assert len(before)==2 and before==after
    assert has_audio(tmp_path/'second.mp4') and abs(probe_duration(tmp_path/'second.mp4')-2)<.1
