"""Regression fixtures exercise browser findings, rather than trusting clean plan data."""
import shutil
from pathlib import Path
import pytest
from engine.hyperframes import builder, quality
from engine.hyperframes.schema import VisualBeat


def test_comparison_has_only_grounded_labels():
    beat=VisualBeat(id='comparison',start=0,end=3,title='۲ انتخاب',visual_type='comparison',items=['برای خانه','برای سفر'])
    markup=builder._beat_markup(beat)
    assert '∞' not in markup and '×۱' not in markup
    assert 'برای خانه' in markup and 'برای سفر' in markup


def test_kinetic_preserves_joined_words():
    beat=VisualBeat(id='kinetic',start=0,end=3,title='انتخاب بهتر در ۳ گام',visual_type='kinetic_type')
    markup=builder._beat_markup(beat)
    assert markup.count('class="kinetic-word"')==5
    assert '>انتخاب</span>' in markup
    assert '.kinetic-word' in builder._timeline_script([beat])


def browser_project(tmp_path,body):
    root=Path(__file__).resolve().parents[1]
    if not shutil.which('node') or not (root/'web/node_modules/playwright').exists():pytest.skip('browser QC requires web npm dependencies')
    (tmp_path/'index.html').write_text('<html lang="fa"><body style="margin:0;width:1080px;height:1920px">'+body+'</body></html>')
    return tmp_path


@pytest.mark.parametrize('body,finding',[
    ('<section class="visual-beat" data-start="0" data-duration="3"><b data-qc="chrome">Cue 01</b></section>','non-Persian'),
    ('<section class="visual-beat" data-start="0" data-duration="3"><b data-qc="chrome" style="opacity:0">Hidden badge 01</b></section>','non-Persian'),
    ('<section class="visual-beat" data-start="0" data-duration="3"><b data-qc="chrome">42</b></section>','non-Persian'),
    ('<section class="visual-beat" data-start="0" data-duration="3" style="width:80px;height:30px;overflow:hidden"><div style="width:600px">انتخاب بهتر برای خانه</div></section>','outside panel'),
    ('<section id="s1" class="clip scene" data-start="0" data-duration="3"><img id="s1pr" style="opacity:0"></section>','no product pixels'),
])
def test_browser_rejects_actual_defective_frame(tmp_path,body,finding):
    project=browser_project(tmp_path,body)
    report=quality.review_project(project,tmp_path/'qc')
    if report.get('unavailable'):pytest.fail(str(report))
    assert not report['passed']
    assert any(finding in p for p in report['problems']),report


def test_browser_accepts_persian_panel(tmp_path):
    project=browser_project(tmp_path,'<section class="visual-beat" data-start="0" data-duration="3" style="width:1000px;height:800px;font-size:64px">انتخاب ۱۲ گام</section>')
    assert quality.review_project(project,tmp_path/'qc')['passed']


def test_browser_accepts_script_brand_model_and_localized_digits(tmp_path):
    from engine.persian_text import display_text
    title = display_text('کفش Nike Air سایز 42 مدل A52 و iPhone 15')
    assert title == 'کفش Nike Air سایز ۴۲ مدل A52 و iPhone 15'
    project=browser_project(tmp_path,f'<section class="visual-beat" data-start="0" data-duration="3" style="font-size:60px">{title}<b data-qc="chrome">ویژگی محصول ۰۱</b></section>')
    assert quality.review_project(project,tmp_path/'qc')['passed']


def test_vendored_content_allows_brand_but_chrome_is_checked(tmp_path):
    import json,subprocess
    from creative import panel_library as lib
    from engine.hyperframes.assets import ensure_gsap
    browser_project(tmp_path,'')
    assets=tmp_path/'assets/fonts';assets.mkdir(parents=True)
    shutil.copy2(ensure_gsap(),tmp_path/'assets/gsap.min.js')
    shutil.copy2(Path(__file__).resolve().parents[1]/'presets/fonts/RAY-EXTRABOLD.TTF',assets/'ray-extrabold.ttf')
    source=lib.install(tmp_path,'push-in')
    page=source.parent/'index.html'
    page.write_text(source.read_text().replace('<template>','').replace('</template>',''))
    request=tmp_path/'request.json'
    request.write_text(json.dumps({'project':str(page.parent),'componentUi':True,'variables':{'text':'Nike A52'},'samples':[2],'width':605,'height':555}))
    command=['node',str(Path(__file__).resolve().parents[1]/'scripts/motion_dom_qc.mjs'),str(request)]
    report=json.loads(subprocess.check_output(command,text=True))
    assert not report['findings'],report
    page.write_text(page.read_text().replace('<body>','<body><b data-qc="chrome">English UI 01</b>'))
    report=json.loads(subprocess.check_output(command,text=True))
    assert any('English UI 01' in f['message'] for f in report['findings'])


@pytest.mark.parametrize('source,expected',[
    ('در 42 روز با 2.5 درصد رشد','در ۴۲ روز با ۲٫۵ درصد رشد'),
    ('کفش Nike Air سایز 42','کفش Nike Air سایز ۴۲'),
    ('iPhone 15 و A52 با 5G و 20% تخفیف','iPhone 15 و A52 با 5G و ۲۰٪ تخفیف'),
    ('iPhone 15، تعداد 2','iPhone 15، تعداد ۲'),
])
def test_display_digits_match_both_engines(source,expected):
    import json, subprocess
    from engine.persian_text import display_text
    assert display_text(source)==expected
    result=subprocess.check_output(['node','--input-type=module','-e',
        "import {displayText} from './remotion/src/persian-text.mjs'; console.log(JSON.stringify(displayText(JSON.parse(process.argv[1]))));",json.dumps(source)],text=True,cwd=Path(__file__).resolve().parents[1])
    assert json.loads(result)==expected


def test_latin_title_runs_keep_source_order_in_both_engines():
    import json,subprocess
    from engine.persian_text import display_units
    source='کفش Nike Air سایز 42 مدل iPhone 15 و A52'
    expected=['کفش','Nike Air','سایز','۴۲','مدل','iPhone 15','و','A52']
    assert display_units(source)==expected
    result=subprocess.check_output(['node','--input-type=module','-e',
        "import {displayUnits} from './remotion/src/persian-text.mjs'; console.log(JSON.stringify(displayUnits(JSON.parse(process.argv[1]))));",json.dumps(source)],text=True,cwd=Path(__file__).resolve().parents[1])
    assert json.loads(result)==expected


@pytest.mark.parametrize('continuous',[False,True])
@pytest.mark.parametrize('items',[[],[''],['برای خانه']])
def test_incomplete_comparison_resolves_before_render(continuous,items):
    from types import SimpleNamespace as NS
    plan=NS(continuous_split=continuous,duration=8,shots=[NS(src_in=0,src_out=8,out_start=0)])
    decisions={'storyboard':[{'i':0,'title':'مقایسه برای انتخاب بهتر','visual_type':'comparison','items':items}]}
    transcript={'sentences':[{'start':0,'end':8,'text':'مقایسه برای انتخاب بهتر'}]}
    beat,=builder.build_visual_beats(plan,decisions,transcript)
    assert beat.visual_type=='kinetic_type'
    assert 'requires two non-empty labels' in beat.why
    assert 'class="compare"' not in builder._beat_markup(beat)


def test_template_digit_conversion_preserves_source_and_caption_timing():
    import random
    from engine.hyperframes import product_reel
    scene={'asset':'photo.png','title':'کفش Nike Air سایز 42 مدل A52','frames':90,'caption_timing':'aligned',
           'caption_words':[{'w':w,'start':i*.3,'end':i*.3+.25} for i,w in enumerate('مدل iPhone 15 با 2 رنگ'.split())]}
    markup,js=product_reel._scene_html(1,scene,3,3,.3,3,random.Random(0))
    assert '>۴۲</span>' in markup and '>A52</span>' in markup
    assert '>15</span>' in markup and '>۲</span>' in markup
    assert scene['title'].endswith('42 مدل A52') and scene['caption_words'][4]['w']=='2'
    assert any('opacity:.6,y:16' in line and 'duration:0.3' in line for line in js)
    assert any('scale:1.06,duration:0.3' in line for line in js)


@pytest.mark.parametrize('look',[None,'classic','cinematic'])
def test_remotion_look_defaults_classic_and_honours_override(tmp_path,monkeypatch,look):
    import io,json
    from types import SimpleNamespace as NS
    from engine import remotion_renderer
    photo=tmp_path/'image.png';photo.write_bytes(b'owned')
    if look is None:monkeypatch.delenv('REMOTION_LOOK',raising=False)
    else:monkeypatch.setenv('REMOTION_LOOK',look)
    process=NS(stdout=io.StringIO(''),poll=lambda:0,wait=lambda:0)
    monkeypatch.setattr('subprocess.Popen',lambda *a,**kw:process)
    remotion_renderer.render({'version':2,'scenes':[{'asset':str(photo),'frames':60,'kind':'photo','title':'مدل A52'}]},tmp_path/'out.mp4',job_dir=tmp_path,captions_prepared=True)
    assert json.loads((tmp_path/'out.remotion.json').read_text())['look']==(look or 'classic')


@pytest.mark.parametrize('kind,items',[
    ('comparison',['انتخاب مناسب برای استفاده در خانه','انتخاب مناسب برای سفرهای روزانه']),
    ('steps',['انتخاب دقیق برای نیازهای هر روز','مقایسه قیمت پیش از خرید محصول','خرید آسان برای استفاده در خانه','بررسی کیفیت پس از خرید محصول']),
])
def test_long_persian_items_fit_real_panel(tmp_path,monkeypatch,kind,items):
    browser_project(tmp_path, '')
    # A local GSAP-shaped clock is sufficient for static hold layout; no remote dependency.
    gsap=tmp_path/'clock.js'
    gsap.write_text('window.gsap={timeline:()=>({fromTo(){return this},to(){return this},seek(){document.querySelectorAll(".beat-inner").forEach(e=>e.style.opacity=1);return this}})};')
    monkeypatch.setattr('engine.hyperframes.assets.ensure_gsap',lambda:gsap)
    project=tmp_path/'project'
    beat=VisualBeat(id='long',start=0,end=4,title='۳ گام برای انتخاب بهتر',visual_type=kind,items=items)
    builder.build_project(project,tmp_path/'base.mp4',[beat],duration=4,enable_registry=False)
    assert quality.review_project(project,tmp_path/'qc')['passed']
