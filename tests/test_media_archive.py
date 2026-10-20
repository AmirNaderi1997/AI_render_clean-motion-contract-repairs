import base64
import pytest
from brain import media_archive as archive


def test_archive_is_content_addressed_and_local(monkeypatch,tmp_path):
    monkeypatch.setattr(archive,'root',lambda:tmp_path)
    raw=b'\x89PNG'+b'x'*32
    item=archive.images({'data':[{'b64_json':base64.b64encode(raw).decode()}]})[0]
    assert archive.resolve(item['id']).read_bytes()==raw
    assert archive.save(raw,'image/png')==item
    assert len(list(tmp_path.iterdir()))==1
    with pytest.raises(ValueError):archive.resolve('../secret.png')
    assert archive.images({'data':[{'url':'https://example.invalid/never-fetch'}]})==[]
