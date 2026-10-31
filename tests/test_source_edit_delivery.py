"""Regression coverage for the real cached-shot -> concat -> delivery encode."""
import json
import shutil
import subprocess
from fractions import Fraction

import pytest

from engine.talking_styles import talking_1 as reel


@pytest.mark.parametrize('hook', ['', '   \t\n'])
def test_empty_hook_has_no_background_or_text(monkeypatch, hook):
    # Font metrics are irrelevant to admission: inspect actual ASS drawing events.
    monkeypatch.setattr(reel, 'measure_text_boxes',
                        lambda texts, *a: [(len(t) * 20, -40, 10) for t, _ in texts])
    plan = reel.ReelPlan(shots=[], duration=2,
                         captions=[{'start': 0, 'end': 2, 'text': 'آزمون فارسی'}])
    ass = reel.build_ass(plan, hook, [], '', '', None)
    events = [line for line in ass.splitlines() if line.startswith('Dialogue:')]
    assert len(events) == 2  # caption background and Persian text only
    assert all(line.startswith(('Dialogue: 3,', 'Dialogue: 4,')) for line in events)
    assert 'آزمون' in ass
    control = reel.build_ass(plan, 'عنوان', [], '', '', None)
    assert 'Dialogue: 1,' in control and ',hook,,' in control


def test_cut_join_delivery_is_exact_cfr_with_audio_sync(monkeypatch, tmp_path):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg/ffprobe required for real encoding regression')
    # Exercise the complete media encode locally even where FFmpeg lacks libass.
    # ASS drawing admission is covered separately above; no composition/encode is mocked.
    monkeypatch.setattr(reel, 'ass_burner_ffmpeg', lambda: ffmpeg)
    monkeypatch.setattr(reel, 'subtitles_filter', lambda *a: 'null')
    monkeypatch.setattr(reel, 'fonts_bundle', lambda *a: None)
    monkeypatch.setattr(reel, 'measure_text_boxes',
                        lambda texts, *a: [(len(t) * 10, -8, 2) for t, _ in texts])
    monkeypatch.setattr(reel, 'W', 180)
    monkeypatch.setattr(reel, 'H', 320)
    source = tmp_path / 'source.mp4'
    # A pulse at source 1.9s exposes any audio shift across the pause cut.
    subprocess.run([ffmpeg, '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    'testsrc2=size=180x320:rate=60:duration=3', '-f', 'lavfi', '-i',
                    r'aevalsrc=if(between(t\,1.9\,2.0)\,0.5*sin(2*PI*500*t)\,0):s=48000:d=3',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', str(source)], check=True, capture_output=True)
    shots = [reel.Shot(0.127, 1.144), reel.Shot(1.724, 2.743, out_start=1.017)]
    duration = sum(s.length for s in shots)
    plan = reel.ReelPlan(shots=shots, duration=duration)
    out = tmp_path / 'delivery.mp4'
    reel.render(source, plan, out, hook='', highlight=[], name='', title='',
                work_dir=tmp_path / 'work', render_settings={
                    'outro_logo': {'enabled': False}, 'zoom': {'enabled': False},
                    'grade': {'vignette': 0}})
    data = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
                                               '-show_frames', '-of', 'json', str(out)]))
    video = next(s for s in data['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in data['streams'] if s['codec_type'] == 'audio')
    assert video['avg_frame_rate'] == video['r_frame_rate'] == '30/1'
    assert abs(float(video['duration']) - duration) <= 1 / 30
    assert abs(float(audio['duration']) - float(video['duration'])) <= 1 / 30
    pts = [Fraction(f['pts']) * Fraction(video['time_base']) for f in data['frames']
           if f['media_type'] == 'video']
    assert all(b - a == Fraction(1, 30) for a, b in zip(pts, pts[1:]))
    import array
    pcm = array.array('f', subprocess.check_output([ffmpeg, '-v', 'error', '-i', str(out),
                          '-vn', '-ac', '1', '-ar', '48000', '-f', 'f32le', '-']))
    # Whole-source initial trim also removes 0.127s. Peak window begins at 1.193s.
    expected = 1.017 + (1.9 - 1.724)
    bins = [sum(x*x for x in pcm[i:i+480]) for i in range(0, len(pcm), 480)]
    active = [i / 100 for i, energy in enumerate(bins) if energy > max(bins) * .25]
    assert abs(active[0] - expected) <= 1 / 30
    assert abs(active[-1] + .01 - (expected + .1)) <= 1 / 30
