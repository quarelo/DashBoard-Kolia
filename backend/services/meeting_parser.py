"""Validate meeting imports before persistence or any analysis calls.

CSV and JSON share the same canonical record representation. Transcription
storage preserves the original string; its digest uses NFC and collapsed
Unicode whitespace only. Metadata strings keep case and leading zeroes.
"""

import csv
from dataclasses import dataclass
import hashlib
import io
import json
import math
from pathlib import PurePath
import unicodedata


MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 1000
_ID_FIELDS = ("ID_MEETING", "meeting_id")
_TEXT_FIELDS = ("ANON_TRANSCRICAO", "transcription")
_TITLE_FIELDS = ("TITLE", "title")
_RECORD_FIELDS = frozenset(_ID_FIELDS + _TEXT_FIELDS + _TITLE_FIELDS)

# csv's default 128 KiB field ceiling is too small for meeting transcripts.
# Set a stable process limit rather than temporarily changing shared state.
csv.field_size_limit(max(csv.field_size_limit(), MAX_IMPORT_BYTES))


class ImportValidationError(ValueError):
    def __init__(self, message: str, code: str = "INVALID_IMPORT", status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class ParsedMeeting:
    external_id: str
    title: str
    transcription: str
    metadata: dict
    transcription_hash: str


@dataclass(frozen=True)
class ParsedImport:
    file_hash: str
    content_hash: str
    meetings: list[ParsedMeeting]


def _canonical_text(value: str) -> str:
    if "\x00" in value:
        raise ImportValidationError("O arquivo contém caracteres nulos inválidos.")
    return " ".join(unicodedata.normalize("NFC", value).split())


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ImportValidationError("O JSON contém chaves duplicadas.")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ImportValidationError("O JSON contém um número não finito.")


def _json_rows(text: str) -> list:
    try:
        value = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, ImportValidationError):
            raise
        raise ImportValidationError("O arquivo JSON é inválido.") from None
    if isinstance(value, dict) and set(value) == {"meetings"}:
        value = value["meetings"]
    if not isinstance(value, list):
        raise ImportValidationError("O JSON deve ser uma lista de reuniões ou um objeto com meetings.")
    return value


def _validate_csv_quotes(text: str, delimiter: str) -> None:
    """Reject bare quotes too: csv.reader(strict=True) accepts those in fields."""
    state = "start"
    for char in text:
        if state == "quoted":
            if char == '"':
                state = "after_quote"
        elif state == "after_quote":
            if char == '"':
                state = "quoted"
            elif char == delimiter or char in "\r\n":
                state = "start"
            else:
                raise ImportValidationError("O CSV contém aspas malformadas.")
        elif char == '"':
            if state != "start":
                raise ImportValidationError("O CSV contém aspas malformadas.")
            state = "quoted"
        elif char == delimiter or char in "\r\n":
            state = "start"
        else:
            state = "unquoted"
    if state == "quoted":
        raise ImportValidationError("O CSV contém aspas não fechadas.")


def _csv_rows(text: str) -> list:
    header_line = text.splitlines()[0] if text else ""
    delimiter = ";" if header_line.count(";") > header_line.count(",") else ","
    _validate_csv_quotes(text, delimiter)
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        headers = next(reader, [])
        headers = [_canonical_text(header) for header in headers]
        if not headers or any(not header for header in headers) or len(set(headers)) != len(headers):
            raise ImportValidationError("O CSV precisa de cabeçalhos únicos e não vazios.")
        rows = []
        for index, values in enumerate(reader, start=1):
            if index > MAX_IMPORT_ROWS:
                raise ImportValidationError("O arquivo excede o limite de 1000 reuniões.")
            if len(values) != len(headers):
                raise ImportValidationError(f"A linha de dados {index} tem quantidade inválida de colunas.")
            rows.append(dict(zip(headers, values)))
        return rows
    except csv.Error:
        raise ImportValidationError("O arquivo CSV tem estrutura inválida.") from None


def _field(row: dict, aliases: tuple, required: bool = True):
    matches = [key for key in aliases if key in row]
    if len(matches) > 1:
        raise ImportValidationError("A reunião contém campos equivalentes duplicados.")
    if not matches:
        if required:
            raise ImportValidationError(f"Campo obrigatório ausente: {aliases[0]}.")
        return None
    return row[matches[0]]


def _metadata_scalar(key: str, value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        normalized = _canonical_text(value)
        # This production column is explicitly boolean. Do not reinterpret
        # arbitrary metadata strings (including numeric codes or proper names).
        if key == "FLG_EXTERNO" and normalized.lower() in ("true", "false"):
            return normalized.lower()
        return normalized
    if isinstance(value, (bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ImportValidationError("Os metadados contêm um número não finito.")
        return json.dumps(value, allow_nan=False)
    raise ImportValidationError("Os metadados devem conter somente valores simples.")


def _meeting(raw_row) -> ParsedMeeting:
    if not isinstance(raw_row, dict):
        raise ImportValidationError("Cada reunião deve ser um objeto.")
    row = {}
    for key, value in raw_row.items():
        normalized_key = _canonical_text(key)
        if not normalized_key or normalized_key in row:
            raise ImportValidationError("A reunião contém campos vazios ou duplicados.")
        row[normalized_key] = value
    identifier = _field(row, _ID_FIELDS)
    if isinstance(identifier, bool) or not isinstance(identifier, (str, int)):
        raise ImportValidationError("O identificador da reunião deve ser texto ou inteiro.")
    external_id = _canonical_text(str(identifier))
    if not external_id:
        raise ImportValidationError("O identificador da reunião está vazio.")
    if len(external_id.encode("utf-8")) > 512:
        raise ImportValidationError("O identificador da reunião excede 512 bytes UTF-8.")
    transcription = _field(row, _TEXT_FIELDS)
    if not isinstance(transcription, str) or not _canonical_text(transcription):
        raise ImportValidationError("A reunião precisa de uma transcrição não vazia.")
    title = _field(row, _TITLE_FIELDS, required=False)
    if title is not None and not isinstance(title, str):
        raise ImportValidationError("O título da reunião deve ser texto.")
    title = _canonical_text(title or "") or f"Reunião {external_id}"
    metadata = {key: _metadata_scalar(key, value) for key, value in row.items() if key not in _RECORD_FIELDS}
    return ParsedMeeting(external_id, title, transcription, metadata, _digest(_canonical_text(transcription)))


def parse_meeting_file(content: bytes, filename: str) -> ParsedImport:
    """Parse and validate a complete bounded upload without side effects or IA."""
    if len(content) > MAX_IMPORT_BYTES:
        raise ImportValidationError("O arquivo excede o limite de 5 MiB.", "FILE_TOO_LARGE", 413)
    extension = PurePath(filename).suffix.lower()
    if extension not in (".csv", ".json"):
        raise ImportValidationError("Formato não suportado. Envie CSV ou JSON.", "UNSUPPORTED_FORMAT", 415)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportValidationError("O arquivo deve usar codificação UTF-8.") from None
    if not text.strip() or "\x00" in text:
        raise ImportValidationError("O arquivo está vazio ou contém dados binários.")
    rows = _csv_rows(text) if extension == ".csv" else _json_rows(text)
    if not rows:
        raise ImportValidationError("O arquivo precisa conter pelo menos uma reunião.")
    if len(rows) > MAX_IMPORT_ROWS:
        raise ImportValidationError("O arquivo excede o limite de 1000 reuniões.")
    meetings = []
    identifiers = set()
    try:
        for row in rows:
            meeting = _meeting(row)
            if meeting.external_id in identifiers:
                raise ImportValidationError("O arquivo contém identificadores de reunião duplicados.", "DUPLICATE_MEETING_IN_FILE")
            identifiers.add(meeting.external_id)
            meetings.append(meeting)
        canonical = [
            {"meeting_id": meeting.external_id, "title": meeting.title,
             "transcription": _canonical_text(meeting.transcription), "metadata": meeting.metadata}
            for meeting in sorted(meetings, key=lambda item: item.external_id)
        ]
        content_hash = _digest(json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    except UnicodeError:
        raise ImportValidationError("O arquivo contém caracteres Unicode inválidos.") from None
    return ParsedImport(hashlib.sha256(content).hexdigest(), content_hash, meetings)
