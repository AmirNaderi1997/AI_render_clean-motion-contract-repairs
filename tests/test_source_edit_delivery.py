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


@pytest.mark.parametrize('ranges,source_duration,pulse', [
    ([(.127, 1.144), (1.724, 2.743)], 3, 1.9),
    # The deployed 13-segment pause-removal pattern exposes concat EOF rounding.
    ([(.571, .951), (2.453, 4.376), (5.057, 6.619), (9.282, 10.244),
      (17.834, 20.277), (25.023, 30.611), (30.611, 35.357), (35.357, 40.063),
      (40.304, 41.565), (41.846, 43.147), (43.508, 50.858),
      (51.659, 55.284), (56.305, 60.5)], 61, 39.73),
])
def test_cut_join_delivery_is_exact_cfr_with_audio_sync(monkeypatch, tmp_path,
                                                       ranges, source_duration, pulse):
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
    # A pulse inside a retained shot exposes audio shifts across pause cuts.
    subprocess.run([ffmpeg, '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    f'testsrc2=size=180x320:rate=60:duration={source_duration}', '-f', 'lavfi', '-i',
                    fr'aevalsrc=if(between(t\,{pulse}\,{pulse+.1})\,0.5*sin(2*PI*500*t)\,0):s=48000:d={source_duration}',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', str(source)], check=True, capture_output=True)
    shots = []
    elapsed = 0.
    for start, end in ranges:
        shots.append(reel.Shot(start, end, out_start=elapsed))
        elapsed += end - start
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
    shot = next(s for s in shots if s.src_in <= pulse < s.src_out)
    expected = shot.out_start + pulse - shot.src_in
    bins = [sum(x*x for x in pcm[i:i+480]) for i in range(0, len(pcm), 480)]
    active = [i / 100 for i, energy in enumerate(bins) if energy > max(bins) * .25]
    assert abs(active[0] - expected) <= 1 / 30
    assert abs(active[-1] + .01 - (expected + .1)) <= 1 / 30
