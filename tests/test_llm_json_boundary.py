import pytest
from brain.llm import _extract_json


@pytest.mark.parametrize('text', ['{"assets":[]}', '```json\n{"assets":[]}\n```',
    '```json\n{"assets":[]}\n```\nتوضیح دربارهٔ نتیجه'])
def test_one_json_document_with_optional_fence_and_prose(text):
    assert _extract_json(text) == {'assets': []}


@pytest.mark.parametrize('text', ['{"assets":[]}\n{"other":1}',
    '```json\n{"a":1}\n```\n```json\n{"b":2}\n```',
    '```json\n{"a":1}\n```\n{"b":2}', '```json\n{"broken":}\n```'])
def test_ambiguous_or_invalid_documents_do_not_become_executable_plans(text):
    with pytest.raises(ValueError): _extract_json(text)
