"""Offline tests for the AI ingestion edge (mocked SDK, no key, no network).

We inject a fake Anthropic client whose `messages.parse` returns a Pydantic
schema instance (mirroring the real SDK's `parsed_output`), and assert:
  * variant extraction maps gene/hgvs/classification and drops gene-less rows;
  * phenotype extraction flows through HPO grounding (LLM proposes, HPO
    validates), keeping the grounded terms and reporting the ungrounded ones;
  * typed SDK exceptions surface as a single LLMError.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import unittest
from unittest import mock

from phenofit import extract, llm
from phenofit.llm import PhenotypeExtraction, ReportedVariantOut, VariantExtraction
from phenofit.models import Phenotype

SEIZURE = Phenotype("HP:0001250", "Seizure")
ATAXIA = Phenotype("HP:0001251", "Ataxia")


class _FakeMessages:
    def __init__(self, parsed):
        self._parsed = parsed

    def parse(self, **_kwargs):
        return mock.Mock(parsed_output=self._parsed)


class _FakeClient:
    def __init__(self, parsed):
        self.messages = _FakeMessages(parsed)


class VariantExtractionTests(unittest.TestCase):
    def test_maps_fields_and_drops_geneless(self):
        parsed = VariantExtraction(variants=[
            ReportedVariantOut(gene="SCN1A", hgvs="c.3637C>T", classification="Pathogenic"),
            ReportedVariantOut(gene="", hgvs="c.1A>T"),  # no gene -> dropped
            ReportedVariantOut(gene="FBN1"),
        ])
        out = llm.extract_variants_raw("report text", sdk_client=_FakeClient(parsed))
        self.assertEqual([v["gene"] for v in out], ["SCN1A", "FBN1"])
        self.assertEqual(out[0]["hgvs"], "c.3637C>T")
        self.assertEqual(out[0]["classification"], "Pathogenic")
        self.assertEqual(out[1]["hgvs"], "")


class PhenotypeGroundingTests(unittest.TestCase):
    def test_llm_proposes_hpo_validates(self):
        parsed = PhenotypeExtraction(phrases=["seizure", "ataxia", "made up nonsense"])
        fake = _FakeClient(parsed)

        def fake_resolve(_client, phrase):
            return {"seizure": SEIZURE, "ataxia": ATAXIA}.get(phrase)

        with mock.patch.object(extract, "resolve_term", fake_resolve):
            result = extract.extract_from_notes(None, "notes", sdk_client=fake)

        self.assertEqual([e.phenotype.hpo_id for e in result.phenotypes],
                         ["HP:0001250", "HP:0001251"])
        self.assertEqual(result.ungrounded, ["made up nonsense"])

    def test_ingest_report_combines_variants_and_phenotypes(self):
        parsed_variants = VariantExtraction(variants=[
            ReportedVariantOut(gene="SCN1A", hgvs="c.3637C>T", classification="Pathogenic"),
        ])
        parsed_phenos = PhenotypeExtraction(phrases=["seizure"])

        # ingest_report calls variants first, then phenotypes: give a client
        # whose parse() returns the right schema based on the requested type.
        class _RoutingMessages:
            def parse(self, **kwargs):
                fmt = kwargs.get("output_format")
                parsed = parsed_variants if fmt is VariantExtraction else parsed_phenos
                return mock.Mock(parsed_output=parsed)

        class _RoutingClient:
            messages = _RoutingMessages()

        with mock.patch.object(extract, "resolve_term", lambda _c, p: SEIZURE if p == "seizure" else None):
            ingest = extract.ingest_report(None, "report text", sdk_client=_RoutingClient())

        self.assertEqual(ingest.variants[0]["gene"], "SCN1A")
        self.assertEqual(len(ingest.phenotypes.phenotypes), 1)


class ErrorMappingTests(unittest.TestCase):
    def test_not_configured_without_key(self):
        import os
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(llm.is_configured())

    def test_typed_sdk_exceptions_become_llmerror(self):
        import anthropic

        class _Boom:
            def __init__(self, exc):
                self._exc = exc

            @property
            def messages(self):
                boom = self._exc

                class _M:
                    def parse(self, **_kw):
                        raise boom
                return _M()

        # A connection error is the simplest typed exception to construct.
        conn_err = anthropic.APIConnectionError(request=mock.Mock())
        with self.assertRaises(llm.LLMError):
            llm.extract_variants_raw("x", sdk_client=_Boom(conn_err))


if __name__ == "__main__":
    unittest.main()
