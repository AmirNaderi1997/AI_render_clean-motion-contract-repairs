import pytest

from engine import music_mix


def test_defaults_reproduce_the_original_filter_text_exactly():
    # style 1 as it was hard-coded in the renderer
    mix = music_mix.resolve("talking_1", {})
    assert mix.bed(3, 40.0) == ("[3:a]atrim=0:40.000,volume=-19.0dB,afade=t=in:d=0.8,afade=t=out:st=38.400:d=1.6,"
                                "aresample=48000,aformat=channel_layouts=stereo[m]")
    assert mix.graph("T") == ["[cpad]aresample=48000,aformat=channel_layouts=stereo,asplit[vo][key]",
                              "[m][key]sidechaincompress=threshold=0.03:ratio=5:attack=50:release=500[duck]",
                              "[vo][duck]amix=inputs=2:normalize=0:duration=first,T"]
    two = music_mix.resolve("talking_2", None)
    assert two.bed(1, 20.0) == ("[1:a]atrim=0:20.000,volume=-15.0dB,afade=t=in:d=0.5,afade=t=out:st=18.400:d=1.6,"
                                "aresample=48000,aformat=channel_layouts=stereo[m]")
    assert "ratio=4:attack=40:release=400" in two.graph("T")[1]
    three = music_mix.resolve("talking_3", {})
    assert "volume=-14.0dB,afade=t=in:d=0.8,afade=t=out:st=18.200:d=1.8," in three.bed(1, 20.0)
    assert "ratio=4:attack=50:release=500" in three.graph("T")[1]


def test_overrides_change_volume_fades_and_ducking():
    mix = music_mix.resolve("talking_2", {"music_mix": {"volume_db": -24, "fade_in": 0, "fade_out": 3, "duck": False}})
    assert "volume=-24.0dB,afade=t=out:st=17.000:d=3.0,aresample" in mix.bed(1, 20.0)
    assert "afade=t=in" not in mix.bed(1, 20.0)                                  # a zero fade is no filter at all
    assert mix.graph("T") == ["[cpad]aresample=48000,aformat=channel_layouts=stereo[vo]",
                              "[vo][m]amix=inputs=2:normalize=0:duration=first,T"]


def test_clean_rejects_bad_values_and_keeps_good_ones():
    assert music_mix.clean({"volume_db": -22.04, "fade_out": "2", "duck": 0, "junk": 1}) == {"volume_db": -22.0, "fade_out": 2.0, "duck": False}
    assert music_mix.clean(None) == {}
    for bad in ({"volume_db": 5}, {"fade_in": -1}, {"fade_out": 99}, {"volume_db": "loud"}, []):
        with pytest.raises(ValueError):
            music_mix.clean(bad)
