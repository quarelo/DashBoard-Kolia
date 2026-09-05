"""Import validation exercises real CSV/JSON bytes without network dependencies."""

import csv
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class MeetingParserTests(unittest.TestCase):
    def setUp(self):
        try:
            self.parser = importlib.import_module("services.meeting_parser")
        except ModuleNotFoundError:
            self.fail("The meeting import parser has not been implemented")

    def parse(self, value, filename="meetings.json"):
        content = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        return self.parser.parse_meeting_file(content, filename)

    def assert_invalid(self, value, filename="meetings.json", status=422):
        with self.assertRaises(self.parser.ImportValidationError) as raised:
            self.parse(value, filename)
        self.assertEqual(raised.exception.status_code, status)
        self.assertTrue(raised.exception.code)

    def test_production_csv_preserves_raw_transcription_and_metadata(self):
        content = '\ufeffID_MEETING;ANON_TRANSCRICAO;UF;NOTA_NPS\r\n001;"Olá, equipe.\n  Próxima etapa.";SP;9\r\n'.encode()
        result = self.parse(content, "upload.CSV")
        self.assertEqual(result.file_hash, hashlib.sha256(content).hexdigest())
        self.assertEqual(len(result.meetings), 1)
        meeting = result.meetings[0]
        self.assertEqual(meeting.external_id, "001")
        self.assertEqual(meeting.title, "Reunião 001")
        self.assertEqual(meeting.transcription, "Olá, equipe.\n  Próxima etapa.")
        self.assertEqual(meeting.metadata, {"UF": "SP", "NOTA_NPS": "9"})

    def test_json_wrapper_accepts_normalized_fields_and_title(self):
        result = self.parse({"meetings": [{"meeting_id": " M1 ", "title": "  Vendas  ", "transcription": "  Texto bruto\n", "count": 2, "enabled": True, "missing": None}]})
        meeting = result.meetings[0]
        self.assertEqual(meeting.external_id, "M1")
        self.assertEqual(meeting.title, "Vendas")
        self.assertEqual(meeting.transcription, "  Texto bruto\n")
        self.assertEqual(meeting.metadata, {"count": "2", "enabled": "true", "missing": ""})

    def test_hash_is_stable_across_order_format_and_canonical_whitespace(self):
        csv_content = 'ID_MEETING,ANON_TRANSCRICAO,NOTA_NPS,active,empty\nB,"Cafe\u0301\n  texto",9,true,\nA,Outra fala,7,false,\n'.encode()
        csv_result = self.parse(csv_content, "a.csv")
        json_result = self.parse([
            {"ID_MEETING": "A", "ANON_TRANSCRICAO": "Outra fala", "NOTA_NPS": 7, "active": False, "empty": None},
            {"ID_MEETING": "B", "ANON_TRANSCRICAO": "Café texto", "NOTA_NPS": 9, "active": True, "empty": ""},
        ])
        self.assertEqual(csv_result.content_hash, json_result.content_hash)
        self.assertNotEqual(csv_result.file_hash, json_result.file_hash)
        self.assertEqual(csv_result.meetings[0].transcription_hash, hashlib.sha256("Café texto".encode()).hexdigest())

    def test_hash_preserves_case_punctuation_ids_and_metadata(self):
        base = {"meeting_id": "01", "transcription": "Texto.", "UF": "SP"}
        original = self.parse([base])
        for change in ({"transcription": "texto."}, {"transcription": "Texto"}, {"meeting_id": "1"}, {"UF": "RJ"}):
            with self.subTest(change=change):
                self.assertNotEqual(original.content_hash, self.parse([{**base, **change}]).content_hash)

    def test_same_transcription_with_distinct_ids_remains_two_meetings(self):
        result = self.parse([{"meeting_id": identifier, "transcription": "Mesmo texto"} for identifier in ("1", "2")])
        self.assertEqual(len(result.meetings), 2)
        self.assertEqual(result.meetings[0].transcription_hash, result.meetings[1].transcription_hash)

    def test_numeric_id_and_known_boolean_metadata_match_csv(self):
        csv_result = self.parse(b'ID_MEETING,ANON_TRANSCRICAO,FLG_EXTERNO\n1000000,Texto,True\n', "a.csv")
        json_result = self.parse([{"ID_MEETING": 1000000, "ANON_TRANSCRICAO": "Texto", "FLG_EXTERNO": True}])
        self.assertEqual(csv_result.content_hash, json_result.content_hash)
        self.assertEqual(json_result.meetings[0].external_id, "1000000")
        self.assert_invalid([{"ID_MEETING": 1000000, "ANON_TRANSCRICAO": None}])

    def test_duplicate_ids_are_rejected_after_canonical_normalization(self):
        self.assert_invalid([{"meeting_id": identifier, "transcription": "Texto"} for identifier in ("Café", " Cafe\u0301 ")])
        self.assert_invalid(b"ID_MEETING,ANON_TRANSCRICAO\n1,Texto\n1,Outro\n", "a.csv")

    def test_invalid_json_structures_and_missing_fields_are_rejected(self):
        for value in ([], {}, {"meetings": []}, {"meetings": [], "extra": 1}, [1], [{"id": "1", "title": "Snippet"}], [{"meeting_id": "1"}], [{"meeting_id": "", "transcription": "x"}], [{"meeting_id": "1", "transcription": " \n"}], [{"meeting_id": "1", "transcription": 123}], [{"meeting_id": False, "transcription": "x"}], [{"meeting_id": "1", "transcription": "x", "nested": {}}], [{"meeting_id": "1", "transcription": "x", "nested": []}]):
            with self.subTest(value=value):
                self.assert_invalid(value)

    def test_duplicate_keys_nonfinite_and_deep_json_are_rejected(self):
        for content in (b'[{"meeting_id":"1","meeting_id":"2","transcription":"x"}]', b'[{"meeting_id":"1","transcription":"x","value":NaN}]', b'[{"meeting_id":"1","transcription":"x","value":Infinity}]', b'[{"meeting_id":"1","transcription":"x","value":1e999}]', b'[' * 1100 + b']' * 1100):
            with self.subTest(length=len(content)):
                self.assert_invalid(content)

    def test_ambiguous_aliases_are_rejected(self):
        self.assert_invalid([{"ID_MEETING": "1", "meeting_id": "1", "ANON_TRANSCRICAO": "x"}])

    def test_json_escaped_invalid_unicode_or_null_is_rejected(self):
        for content in (b'[{"meeting_id":"1","transcription":"te\\u0000xt"}]', b'[{"meeting_id":"1","transcription":"\\ud800"}]', b'[{"meeting_id":"1","transcription":"x","field\\u0000":1}]'):
            with self.subTest(content=content):
                self.assert_invalid(content)

    def test_csv_quotes_and_record_aliases_preserve_effective_content(self):
        content = b'meeting_id,title,transcription\r\n1,Demo,"He said ""hello"".\r\nNext line."\r\n'
        result = self.parse(content, "a.csv")
        self.assertEqual(result.meetings[0].transcription, 'He said "hello".\r\nNext line.')
        equivalent = self.parse([{"ID_MEETING": "1", "TITLE": "Demo", "ANON_TRANSCRICAO": 'He said "hello". Next line.'}])
        self.assertEqual(result.content_hash, equivalent.content_hash)
        self.assert_invalid(b'ID_MEETING,ANON_TRANSCRICAO\n1,unquoted"text\n', "a.csv")

    def test_malformed_csv_is_rejected(self):
        for content in (b'', b'ID_MEETING,ANON_TRANSCRICAO\n', b'ID_MEETING,ANON_TRANSCRICAO\n1\n', b'ID_MEETING,ANON_TRANSCRICAO\n1,x,extra\n', b'ID_MEETING,ANON_TRANSCRICAO\n1,"unterminated\n', b'ID_MEETING,ANON_TRANSCRICAO\n1,"text"garbage\n', b'ID_MEETING,ANON_TRANSCRICAO,ID_MEETING\n1,x,2\n', b'ID_MEETING,ANON_TRANSCRICAO,\n1,x,z\n', b'title,transcription\nDemo,x\n'):
            with self.subTest(content=content):
                self.assert_invalid(content, "a.csv")

    def test_invalid_encoding_extension_and_binary_data_are_rejected(self):
        self.assert_invalid(b'\xff', "a.csv")
        self.assert_invalid(b'[]', "a.xlsx", status=415)
        self.assert_invalid(b'ID_MEETING,ANON_TRANSCRICAO\n1,te\x00xt\n', "a.csv")

    def test_size_and_row_limits(self):
        self.assert_invalid(b'x' * (5 * 1024 * 1024 + 1), "a.csv", status=413)
        rows = [{"meeting_id": str(i), "transcription": "x"} for i in range(1000)]
        self.assertEqual(len(self.parse(rows).meetings), 1000)
        self.assert_invalid(rows + [{"meeting_id": "extra", "transcription": "x"}])
        csv_content = ('ID_MEETING,ANON_TRANSCRICAO\n' + ''.join(f'{i},x\n' for i in range(1001))).encode()
        self.assert_invalid(csv_content, "a.csv")

    def test_long_csv_transcription_within_file_limit(self):
        text = "x" * 150_000
        result = self.parse(("ID_MEETING,ANON_TRANSCRICAO\n1," + text + "\n").encode(), "a.csv")
        self.assertEqual(len(result.meetings[0].transcription), 150_000)

    def test_real_dataset_import_and_json_conversion_only_report_aggregates(self):
        path = Path(__file__).resolve().parents[2] / "ia" / "dataset_tratado_revisado.csv"
        if not path.exists():
            self.skipTest("Local POC dataset not present")
        content = path.read_bytes()
        result = self.parse(content, path.name)
        self.assertEqual(len(result.meetings), 500)
        self.assertEqual(len({row.external_id for row in result.meetings}), 500)
        self.assertTrue(all(row.transcription.strip() for row in result.meetings))
        converted = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
        self.assertEqual(result.content_hash, self.parse(converted).content_hash)


if __name__ == "__main__":
    unittest.main()
