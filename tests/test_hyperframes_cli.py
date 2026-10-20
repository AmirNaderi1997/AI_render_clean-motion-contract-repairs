from pathlib import Path

import pytest
from engine.hyperframes.cli import cli_command


def test_missing_runtime_has_actionable_error(monkeypatch, tmp_path):
    monkeypatch.setattr('engine.hyperframes.cli.shutil.which', lambda _: None)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('HYPERFRAMES_CLI', str(tmp_path/'missing'))
    with pytest.raises(RuntimeError, match='rough cut has been preserved'):
        cli_command()


def test_preinstalled_cli_does_not_use_npx(monkeypatch, tmp_path):
    cli = tmp_path/'hyperframes.mjs'
    cli.touch()
    monkeypatch.setenv('HYPERFRAMES_CLI', str(cli))
    monkeypatch.setattr('engine.hyperframes.cli.shutil.which', lambda name: '/bin/node' if name == 'node' else None)
    assert cli_command() == ['/bin/node', str(cli)]


def test_development_npx_is_pinned(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('HYPERFRAMES_CLI', str(tmp_path/'missing'))
    monkeypatch.setattr('engine.hyperframes.cli.shutil.which', lambda name: '/bin/npx' if name == 'npx' else None)
    assert cli_command() == ['/bin/npx', '--yes', 'hyperframes@0.8.161']
