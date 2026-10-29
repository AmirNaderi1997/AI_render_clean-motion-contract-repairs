"""Inspect all enabled, hash-verified adapters at actual panel dimensions."""
import argparse,json,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from creative import panel_library as lib
from engine.hyperframes.assets import ensure_gsap

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=args.output.resolve();(root/'assets/fonts').mkdir(parents=True,exist_ok=True)
    shutil.copy2(ensure_gsap(),root/'assets/gsap.min.js');shutil.copy2('presets/fonts/RAY-EXTRABOLD.TTF',root/'assets/fonts/ray-extrabold.ttf')
    results={}
    for name in sorted(lib.SAFE_COMPONENTS):
        p=lib.install(root,name);shutil.copy2(p,p.parent/'index.html')
        values=lib.LIBRARY[name].fill({'title':'انتخاب ۱۲ گام روشن','items':['انتخاب نخست','مقایسه دقیق','خرید آسان']},4)
        request=root/'request.json';request.write_text(json.dumps({'project':str(p.parent),'variables':values,'samples':[.4,1,2,3.8],
            'width':int(968/lib.LIBRARY[name].zoom),'height':int(888/lib.LIBRARY[name].zoom)}))
        r=subprocess.run(['node',str(Path(__file__).with_name('motion_dom_qc.mjs')),str(request)],text=True,capture_output=True,check=True)
        results[name]=json.loads(r.stdout);print(name,results[name]['findings'],flush=True)
    (root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
