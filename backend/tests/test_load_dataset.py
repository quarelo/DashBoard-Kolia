"""The dataset loader's CSV split and credential lookup; no database, no network.

transcricoes_TOTVS.csv is 38 MiB and 1044 meetings against an upload limit of
5 MiB and 1000 meetings, so the loader has to send it in parts the backend accepts.
"""
import csv
import io

import pytest

from scripts.load_dataset import csv_parts, credentials
from services.meeting_parser import parse_meeting_file

HEADER = ["ID_MEETING", "ANON_TRANSCRICAO", "NOTA_NPS"]


def _csv(rows: list[list[str]], delimiter: str = ",") -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer, delimiter=delimiter, lineterminator="\r\n").writerows([HEADER] + rows)
    return buffer.getvalue().encode("utf-8")


def _meetings(count: int) -> list[list[str]]:
    # Quotes, the delimiter and a line break inside the transcript: what the real CSV has.
    return [[str(index), f'[LOCUTOR 1]: "ok", reunião {index}\nfim ' + "x" * 300, "9"]
            for index in range(count)]


def _ids(parts: list[tuple[bytes, int]]) -> list[str]:
    ids = []
    for part, count in parts:
        meetings = parse_meeting_file(part, "parte.csv").meetings
        assert len(meetings) == count
        ids += [meeting.external_id for meeting in meetings]
    return ids


@pytest.mark.parametrize("max_bytes, max_rows", [(2048, 4), (1024, 1000)])
def test_every_part_is_accepted_and_no_meeting_is_lost_or_reordered(max_bytes, max_rows):
    content = _csv(_meetings(25))

    parts = csv_parts(content, max_bytes=max_bytes, max_rows=max_rows)

    assert len(parts) > 1
    assert all(len(part) <= max_bytes and count <= max_rows for part, count in parts)
    assert _ids(parts) == [str(index) for index in range(25)]


def test_the_same_csv_always_yields_the_same_parts():
    """A re-run must resend identical bytes so the backend answers DUPLICATE_IMPORT."""
    content = _csv(_meetings(12))

    assert csv_parts(content, max_bytes=1024) == csv_parts(content, max_bytes=1024)


def test_semicolon_csv_with_bom_keeps_its_delimiter():
    content = b"\xef\xbb\xbf" + _csv(_meetings(3), delimiter=";")

    parts = csv_parts(content, max_bytes=1024)

    assert all(part.splitlines()[0] == b"ID_MEETING;ANON_TRANSCRICAO;NOTA_NPS" for part, _ in parts)
    assert _ids(parts) == ["0", "1", "2"]


def test_a_meeting_too_big_for_any_part_stops_before_uploading():
    content = _csv([["1", "x" * 5000, "9"]])

    with pytest.raises(ValueError, match="linha de dados 1"):
        csv_parts(content, max_bytes=1024)


def test_credentials_come_from_the_env_file_unless_the_environment_has_them(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_bytes(b"JWT_SECRET=nao-e-daqui\r\nKOLIA_EMAIL=ana@empresa.com\r\nKOLIA_PASSWORD='s3nha'\r\n")
    monkeypatch.delenv("KOLIA_EMAIL", raising=False)
    monkeypatch.delenv("KOLIA_PASSWORD", raising=False)

    assert credentials(str(env_file)) == ("ana@empresa.com", "s3nha")

    monkeypatch.setenv("KOLIA_PASSWORD", "do-ambiente")
    assert credentials(str(env_file)) == ("ana@empresa.com", "do-ambiente")
    assert credentials(str(tmp_path / "nao-existe")) == (None, "do-ambiente")
