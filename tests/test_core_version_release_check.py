"""Release check: `cos update` must name the command that changes the version.

`cos update` re-links assets from the package already on disk, so it can never
move the installed version. Before this, the only signal a stale consumer got
was a drift warning whose suggested fix silenced it.
"""

from __future__ import annotations

import json
import sys
import urllib.error
from io import BytesIO
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cli import core_version, update


class _Response(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def _index_returning(payload: dict):
    return lambda _url, timeout=0: _Response(json.dumps(payload).encode())


def test_latest_published_version_reads_the_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        core_version.urllib.request, "urlopen", _index_returning({"info": {"version": "9.9.9"}})
    )
    assert core_version.latest_published_version() == "9.9.9"


@pytest.mark.parametrize(
    "failure",
    [urllib.error.URLError("offline"), OSError("timed out"), ValueError("not json")],
)
def test_latest_published_version_is_none_when_the_index_is_unreachable(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def _raise(_url, timeout=0):
        raise failure

    monkeypatch.setattr(core_version.urllib.request, "urlopen", _raise)
    assert core_version.latest_published_version() is None


def test_latest_published_version_rejects_a_malformed_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core_version.urllib.request, "urlopen", _index_returning({"info": {}}))
    assert core_version.latest_published_version() is None


def test_release_notice_names_the_new_version_and_the_upgrade_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(update, "latest_published_version", lambda: "0.9.0")

    notice = update._release_notice("0.3.12")

    assert notice is not None
    assert "0.9.0" in notice and "0.3.12" in notice
    assert core_version.UPGRADE_COMMAND in notice
    assert core_version.EDITABLE_UPGRADE_COMMAND in notice


@pytest.mark.parametrize(
    ("latest", "installed"),
    [(None, "0.3.12"), ("0.3.12", "0.3.12"), ("0.9.0", "unknown")],
)
def test_release_notice_stays_silent_when_it_has_nothing_true_to_say(
    monkeypatch: pytest.MonkeyPatch, latest: str | None, installed: str
) -> None:
    monkeypatch.setattr(update, "latest_published_version", lambda: latest)

    assert update._release_notice(installed) is None


def test_update_echoes_the_notice_to_the_operator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Producing the right string is half the fix; `cos update` has to print it.
    from click.testing import CliRunner

    (tmp_path / ".coding-os.yaml").write_text("agents: [claude]\ntemplates: []\n", encoding="utf-8")
    monkeypatch.setattr(update, "latest_published_version", lambda: "9.9.9")
    monkeypatch.setattr(update, "current_core_version", lambda: "0.3.12")
    monkeypatch.setattr(update, "read_stamped_version", lambda _state: "0.3.12")

    result = CliRunner().invoke(update.update, ["-d", str(tmp_path), "--dry-run"])
    # click 8.2 split stderr out of .output; the notice is an operator message.
    emitted = result.output + (result.stderr or "")

    assert "9.9.9" in emitted
    assert core_version.UPGRADE_COMMAND in emitted
