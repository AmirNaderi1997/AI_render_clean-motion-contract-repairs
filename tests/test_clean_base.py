import dataclasses
from types import SimpleNamespace

from app import clean_base


@dataclasses.dataclass
class FakePlan:
    shots: list
    captions: list
    duration: float = 10.0


def planned(captions, shots=("a",), pictures=None):
    return SimpleNamespace(plan=FakePlan(list(shots), captions), pictures=pictures or {}, settings={"zoom": 1}, style="talking_2")


def test_key_ignores_captions_but_follows_everything_else():
    state = {"hook": "h", "music": "m"}
    base = clean_base._key(planned([{"text": "a"}]), state)
    assert base == clean_base._key(planned([{"text": "moved", "look": {"x": 1}}]), state)   # captions never make it stale
    assert base != clean_base._key(planned([], shots=("a", "b")), state)                    # the cut does
    assert base != clean_base._key(planned([], pictures={1: "x.png"}), state)               # so do pictures
    assert base != clean_base._key(planned([]), {**state, "hook": "other"})                 # and the hook


def test_path_for_rejects_unsafe_keys(tmp_path):
    assert clean_base.path_for(tmp_path, "../x") is None
