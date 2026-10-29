"""Offline acceptance through real renderers. Local Majed audio, no provider calls.
Run with JOBS_DIR set to a writable local directory. Photos must be supplied.
"""
from pathlib import Path
import argparse, hashlib, json, math, os, subprocess, sys, wave
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw
from engine.hyperframes import builder,renderer,product_reel,quality,overlay_reel
from engine import remotion_renderer
from creative.style_packs import REFERENCE_AI_NEWS

def run(*args):return subprocess.check_output(list(map(str,args)),stderr=subprocess.PIPE)
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2))
def voice(root,text):
    rate=24000;pcm=bytearray(b'\0\0'*4800);words=[]
    for i,w in enumerate(text.split()):
        src=root/f'w{i}.txt';src.write_text(w.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹','0123456789')))
        run('say','-v','Majed','-f',src,'-o',root/f'w{i}.aiff')
        run('ffmpeg','-v','error','-y','-i',root/f'w{i}.aiff','-ar',rate,'-ac',1,root/f'w{i}.wav')
        with wave.open(str(root/f'w{i}.wav')) as a:data=a.readframes(a.getnframes())
        a=len(pcm)/2/rate;pcm.extend(data);b=len(pcm)/2/rate
        words.append({'w':w,'start':a,'end':b});pcm.extend(b'\0\0'*1200)
    frames=math.ceil(len(pcm)/2/rate*30);pcm.extend(b'\0\0'*max(0,round(frames/30*rate)-len(pcm)//2))
    target=root/'narration.wav'
    with wave.open(str(target),'wb') as a:a.setnchannels(1);a.setsampwidth(2);a.setframerate(rate);a.writeframes(pcm)
    return target,words,frames

def evidence(root,name,video,beats,project,windows):
    probe=json.loads(run('ffprobe','-v','error','-show_streams','-show_format','-of','json',video))
    v=next(s for s in probe['streams'] if s['codec_type']=='video')
    assert (v['width'],v['height'],v['avg_frame_rate'])==(1080,1920,'30/1')
    assert any(s['codec_type']=='audio' for s in probe['streams'])
    save(root/f'{name}-ffprobe.json',probe)
    qc=quality.review_render(video,beats,root/name/'review')
    render_evidence = None
    if video.with_name(video.name+'.render-evidence.json').is_file():
        render_evidence=json.loads(video.with_name(video.name+'.render-evidence.json').read_text())
        problems=quality.review_wipe_witnesses(render_evidence['witnesses'],root/name/'review',video=video)
        qc['problems'].extend(problems);qc['passed'] &= not problems
        qc['status']='passed' if qc['passed'] else 'failed'
    if project:qc['dom']=quality.review_project(project,root/name/'dom',video=video);qc['passed'] &= qc['dom']['passed'];qc['status']='passed' if qc['passed'] else 'failed'
    times=[]
    for a,b in windows:times.extend([a+1/30,(a+b)/2,b-1/30])
    times.extend([a-.15 for a,b in windows[1:]])
    sheet=Image.new('RGB',(360*3,670*math.ceil(len(times)/3)),'#181818')
    for i,t in enumerate(times):
        p=root/f'{name}-{i}.jpg';run('ffmpeg','-v','error','-y','-ss',max(0,t),'-i',video,'-frames:v',1,'-vf','scale=360:640',p)
        sheet.paste(Image.open(p),((i%3)*360,(i//3)*670+30));ImageDraw.Draw(sheet).text(((i%3)*360+8,(i//3)*670+8),f'{t:.3f}s',fill='white')
    sheet.save(root/f'{name}-sheet.jpg')
    result={'video':str(video),'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'qc':qc,'sheet':str(root/f'{name}-sheet.jpg'),'windows':windows,'app_run':False,'render_evidence':render_evidence}
    save(root/f'{name}-result.json',result);print(name,qc['passed'],flush=True);return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);parser.add_argument('--cases',nargs='+');args=parser.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=True)
    results={}
    cases=[('kinetic','انتخاب بهتر در ۳ گام','انتخاب بهتر',[],'kinetic_type'),('comparison','برای ۲ کاربرد سبک برای خانه مناسب برای سفر','برای ۲ کاربرد',['سبک برای خانه','مناسب برای سفر'],'comparison'),('steps','۳ گام برای خرید انتخاب دقیق مقایسه قیمت خرید آسان','۳ گام برای خرید',['انتخاب دقیق','مقایسه قیمت','خرید آسان'],'steps')]
    cases.append(('comparison-empty','مقایسه برای انتخاب بهتر','مقایسه برای انتخاب بهتر',[],'comparison'))
    for name,text,title,items,kind in cases:
        if args.cases and name not in args.cases:continue
        job=root/name;job.mkdir(exist_ok=True);audio,words,frames=voice(job,text);dur=frames/30
        # Exact transcript and identity edit: every displayed title/item occurs in this sentence.
        transcript={'words':words,'sentences':[{'start':0,'end':dur,'text':text}]}
        plan=NS(continuous_split=True,duration=dur,shots=[NS(src_in=0,src_out=dur,out_start=0)])
        decisions={'storyboard':[{'i':0,'title':title,'items':items,'visual_type':kind,'motion_style':'assemble'}]}
        beats=builder.build_visual_beats(plan,decisions,transcript)
        save(job/'input.json',{'transcript':transcript,'decisions':decisions,'beats':[b.model_dump() for b in beats]})
        im=Image.new('RGB',(1080,1920),'#293d46');d=ImageDraw.Draw(im);d.ellipse((385,1080,695,1510),fill='#bf9478');d.rounded_rectangle((260,1480,820,1920),radius=140,fill='#182c54');d.ellipse((455,1240,480,1265),fill='#191919');d.ellipse((600,1240,625,1265),fill='#191919');im.save(job/'speaker.png')
        base=job/'speaker.mp4';run('ffmpeg','-v','error','-y','-loop','1','-framerate','30','-i',job/'speaker.png','-i',audio,'-t',dur,'-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac',base)
        project=job/'hyperframes';builder.build_project(project,base,beats,duration=dur,enable_registry=False)
        video=job/'talking2.mp4';renderer.render_project(project,video,timeout=900)
        results[name]=evidence(root,name,video,beats,project,[(0,dur)])
        if name=='kinetic':
            script={'duration':dur,'use_library':False,'segments':[{'start':0,'end':dur,'layout':'split','beat':{'title':title,'visual_type':kind,'items':[]}}],'words':[]}
            from engine.talking_styles.talking_5 import render_layer
            project=job/'t5work/layer_panel';save(job/'talking5-input.json',script)
            layer=job/'panel.webm';render_layer(NS(script=script,pack=REFERENCE_AI_NEWS),layer,work_dir=job/'t5work',part='panel',timeout=900)
            video=job/'talking5.mp4';run('ffmpeg','-v','error','-y','-i',base,'-c:v','libvpx-vp9','-i',layer,'-filter_complex','[0:v][1:v]overlay=0:0:format=auto','-map','0:a','-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-c:a','copy',video)
            results['kinetic-talking5']=evidence(root,'kinetic-talking5',video,beats,project,[(0,dur)])
    job=root/'product';job.mkdir(exist_ok=True);audio,words,frames=voice(job,'انتخاب بهتر برای 2 کاربرد')
    for name,count in [('hero',1),('promo',3)]:
        if args.cases and name not in args.cases:continue
        config={'version':2,'scenes':[{'asset':str(root/('product-white.jpg' if i%2==0 else 'product-dark.jpg')),'kind':'photo','accent':'#d9b36c','title':['کفش Nike Air سایز 42','مدل A52 برای 2 کاربرد','همراه هر روز'][i],'frames':frames,'narration':str(audio),'narration_text':'انتخاب بهتر برای 2 کاربرد','caption_timing':'aligned','caption_words':words} for i in range(count)]}
        save(job/f'{name}-input.json',config);windows=[(i*frames/30,(i+1)*frames/30) for i in range(count)]
        project=job/name;product_reel.build_project(project,config,job_dir=root,captions_prepared=True)
        video=job/f'{name}-hyperframes.mp4';product_reel.render(config,video,job_dir=root,captions_prepared=True,timeout=900)
        results[name]=evidence(root,name,video,[],project,windows)
        os.environ.pop('REMOTION_LOOK',None)
        os.environ['REMOTION_QC_DIR']=str(job/f'{name}-remotion-wipes')
        video=job/f'{name}-remotion.mp4';remotion_renderer.render(config,video,job_dir=root,captions_prepared=True)
        results[name+'-remotion']=evidence(root,name+'-remotion',video,[],None,windows)
    save(root/'results.json',results)
if __name__=='__main__':main()
