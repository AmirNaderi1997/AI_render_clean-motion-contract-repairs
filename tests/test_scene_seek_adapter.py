import json
import shutil
import subprocess

import pytest

from engine.hyperframes.scenes import scene_script


def test_scene_adapter_forces_seek_safe_from_to_and_preserves_chains():
    if not shutil.which('node'):
        pytest.skip('Node is required for JavaScript adapter test')
    code = scene_script('beat-a', 40, 60, '''
tl.fromTo('a',{opacity:0},{opacity:1,duration:1},T+1)
  .fromTo('b',{x:0},{x:20,duration:1,immediateRender:true},T+2);
tl.set('a',{opacity:0},T);
''', 'full')
    harness = '''const calls=[];
const document={getElementById:()=>({querySelectorAll:()=>[]})};
const tl={fromTo(...args){calls.push(['fromTo',...args]);return this},
set(...args){calls.push(['set',...args]);return this},
to(...args){calls.push(['to',...args]);return this}};
'''
    result = subprocess.run(['node', '-e', harness+code+'\nconsole.log(JSON.stringify(calls));'],
                            capture_output=True, text=True, check=True)
    calls = json.loads(result.stdout)
    tweens = [call for call in calls if call[0]=='fromTo']
    assert len(tweens)==2
    assert all(tween[3]['immediateRender'] is False for tween in tweens)
    assert [tween[4] for tween in tweens]==[41,42]
    assert calls[2]==['set','a',{'opacity':0},40]
