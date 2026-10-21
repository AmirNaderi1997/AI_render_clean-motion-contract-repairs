from html.parser import HTMLParser
from pathlib import Path

from engine.sfx import markup


def test_overlapping_effects_use_separate_reusable_tracks():
    class Parser(HTMLParser):
        clips = []
        def handle_starttag(self, tag, attrs):
            if tag == 'audio':
                self.clips.append(dict(attrs))
    parser = Parser()
    parser.feed(markup([(1, 'whoosh'), (1.38, 'hit'), (5, 'whoosh')], 10,
                       {'whoosh': Path('whoosh.wav'), 'hit': Path('hit.wav')}))
    a, b, c = parser.clips
    assert a['data-track-index'] != b['data-track-index']
    assert a['data-track-index'] == c['data-track-index']
    assert [float(row['data-start']) for row in parser.clips] == [1, 1.38, 5]
