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
    ('<section class="visual-beat" data-start="0" data-duration="3">Cue 01</section>','non-Persian'),
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
