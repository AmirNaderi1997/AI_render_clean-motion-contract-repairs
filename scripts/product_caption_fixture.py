"""Offline narrated fixture: local word audio, mocked ASR, real browser/MP4 renders.

Requires macOS's installed Majed voice, FFmpeg and the project's pinned renderers.
Provider requests are mocked. This is timing acceptance, not a live TTS/STT test.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from engine import narration_alignment, remotion_renderer
from engine.hyperframes import product_reel


def run(*command):
    return subprocess.check_output([str(c) for c in command], stderr=subprocess.PIPE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--gsap', type=Path, help='Use an already installed pinned GSAP asset')
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    tokens = ['این', 'محصول', 'برای', 'خانه', 'شماست']
    # Each word is its own spoken recording. Their concatenation gives known
    # waveform boundaries without guessing speech timing or consuming credits.
    rate = 24000
    pcm = bytearray(b'\0\0' * round(.3 * rate))
    words = []
    for i, token in enumerate(tokens):
        text = root / f'word-{i}.txt';text.write_text(token)
        run('say', '-v', 'Majed', '-f', text, '-o', root / f'word-{i}.aiff')
        target = root / f'word-{i}.wav'
        run('ffmpeg', '-v', 'error', '-y', '-i', root / f'word-{i}.aiff', '-af',
            'silenceremove=start_periods=1:start_threshold=-40dB,areverse,silenceremove=start_periods=1:start_threshold=-40dB,areverse',
            '-ar', rate, '-ac', 1, '-c:a', 'pcm_s16le', target)
        with wave.open(str(target)) as audio:
            sound = audio.readframes(audio.getnframes())
        start = len(pcm) / 2 / rate
        pcm.extend(sound)
        words.append({'w': token, 'start': start, 'end': len(pcm) / 2 / rate})
        pcm.extend(b'\0\0' * round(.3 * rate))
    seconds = len(pcm) / 2 / rate
    frames = math.ceil(seconds * 30)
    pcm.extend(b'\0\0' * max(0, round((frames/30-seconds)*rate)))
    with wave.open(str(root / 'narration.wav'), 'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(rate);audio.writeframes(pcm)
    image = Image.new('RGB', (600, 600), '#214847')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((140, 80, 460, 520), radius=42, fill='#d6b774')
    draw.ellipse((240, 190, 360, 310), fill='#214847')
    image.save(root / 'product.png')
    config = {'version': 2, 'scenes': [{'asset':'product.png', 'narration':'narration.wav',
        'frames':frames, 'kind':'photo', 'accent':'#d6b774', 'title':title,
        'narration_text':' '.join(tokens)} for title in ['انتخاب تازه برای خانه', 'این محصول برای شماست']]}
    (root/'config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2))
    calls = []
    def mocked_stt(*a, **kw):
        calls.append(kw['file_digest'])
        return {'words': words}, 0
    with patch('brain.transcribe_elevenlabs.transcribe_elevenlabs', mocked_stt):
        prepared, evidence = narration_alignment.prepare(config, root)
        # A rerender and the identical second scene share the audio hash cache.
        narration_alignment.prepare(config, root)
    assert len(calls) <= 1 and evidence['caption_timing'] == 'aligned'
    gsap_context = patch('engine.hyperframes.assets.ensure_gsap', lambda: args.gsap.resolve()) if args.gsap else nullcontext()
    with gsap_context:
        project = root / 'hyperframes'
        product_reel.build_project(project, prepared, job_dir=root, captions_prepared=True)
    product_reel._run_cli(project, root/'product-reel.mp4', timeout=600)
    os.environ['REMOTION_LOOK'] = 'cinematic'
    remotion_renderer.render(prepared, root/'remotion-reel.mp4', job_dir=root, captions_prepared=True)

    # One ordinary word onset, then the fifth-word page change in scene two.
    changes = [words[1]['start'], frames/30 + words[4]['start']]
    results, tiles = {}, []
    for name in ['product-reel', 'remotion-reel']:
        video = root / f'{name}.mp4'
        probe = json.loads(run('ffprobe','-v','error','-show_streams','-show_format','-of','json',video))
        v = next(s for s in probe['streams'] if s['codec_type']=='video')
        assert (v['width'],v['height'],v['avg_frame_rate']) == (1080,1920,'30/1')
        assert any(s['codec_type']=='audio' for s in probe['streams'])
        assert abs(float(probe['format']['duration'])-frames*2/30) <= 1/30 + .025
        run('ffmpeg','-v','error','-i',video,'-f','null','-')
        checks = []
        for change_index, at in enumerate(changes):
            onset = math.ceil(at*30 - 1e-7)
            counts = []
            for frame in [onset-1,onset,onset+1]:
                target = root/f'{name}-change{change_index}-frame{frame}.png'
                run('ffmpeg','-v','error','-y','-i',video,'-vf',f'select=eq(n\\,{frame})','-frames:v',1,target)
                source = Image.open(target).convert('RGB')
                caption = source.crop((56,1500,1024,1700))
                gold = sum(r > 150 and g > 115 and b < 155 and r-b > 55 and g-b > 25
                           for r,g,b in caption.getdata())
                counts.append(gold)
                tile = Image.new('RGB',(360,680),'#111111')
                tile.paste(source.resize((360,640)),(0,40))
                ImageDraw.Draw(tile).text((8,10),f'{name}  {frame/30:.3f}s  frame {frame}',fill='white')
                tiles.append(tile)
            # No active word in the preceding gap; highlight appears by +1 frame.
            assert counts[0] < 30 and max(counts[1:]) > 80, (name,at,counts)
            first = next(onset-1+i for i,c in enumerate(counts) if c>80)
            error = first/30-at
            assert abs(error) <= 1/30 + .001
            checks.append({'alignment_start_s':at,'first_highlight_frame':first,
                           'error_s':error,'accent_pixels':counts})
        results[name] = {'width':v['width'],'height':v['height'],'fps':v['avg_frame_rate'],
                         'duration':probe['format']['duration'],'sha256':narration_alignment.audio_hash(video),
                         'decode':'passed','changes':checks}
        (root/f'{name}-ffprobe.json').write_text(json.dumps(probe,indent=2))
    sheet = Image.new('RGB',(1080,680*4),'#111111')
    for i,tile in enumerate(tiles):sheet.paste(tile,((i%3)*360,(i//3)*680))
    sheet.save(root/'word-changes.png')
    report = {'fixture':'local macOS Majed isolated spoken words; mocked ElevenLabs ASR',
              'live_provider_calls':0,'mocked_stt_calls_this_run':len(calls),'words':words,'scene_frames':frames,
              'results':results,'human_audio_review':False,'app_run':False}
    (root/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__ == '__main__':main()
