from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import typer

from nfs_fortaleza.cli import _resolve_nfse_query
from nfs_fortaleza.config import Settings
from nfs_fortaleza.nfse_xml import infer_nfse_period
from nfs_fortaleza.portal import (
    InscricaoNotFoundError,
    InscricaoRow,
    PortalClient,
    _find_inscricao_by_cnpj,
)


class ResolveNfseQueryTests(unittest.TestCase):
    def test_normalizes_cnpj_and_preserves_invoice_number(self) -> None:
        result = _resolve_nfse_query("12.345.678/0001-90", "000123", None, None, None)

        self.assertEqual(result, ("12345678000190", "000123"))

    def test_requires_cnpj_and_invoice_number_together(self) -> None:
        with self.assertRaises(typer.BadParameter):
            _resolve_nfse_query("12345678000190", None, None, None, None)

    def test_rejects_period_filters_in_number_mode(self) -> None:
        with self.assertRaises(typer.BadParameter):
            _resolve_nfse_query("12345678000190", "123", "06/2026", None, None)


class PortalNumberQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        settings = Settings(
            portal_url="https://example.test/grpfor/home.seam",
            cpf_login="00000000000",
            senha="secret",
            database_url="postgresql://example.test/db",
            postgres_schema="test",
        )
        self.client = PortalClient(settings)

    def test_finds_the_exact_registration_cnpj(self) -> None:
        rows = [
            InscricaoRow("0", "11.111.111/0001-11", "100", "Empresa A"),
            InscricaoRow("1", "22.222.222/0001-22", "200", "Empresa B"),
        ]

        selected = _find_inscricao_by_cnpj(rows, "22222222000122")

        self.assertEqual(selected.index, "1")

    def test_does_not_fall_back_to_another_cnpj(self) -> None:
        rows = [InscricaoRow("0", "11.111.111/0001-11", "100", "Empresa A")]

        with self.assertRaises(InscricaoNotFoundError):
            _find_inscricao_by_cnpj(rows, "22222222000122")

    def test_number_query_payload_uses_the_portal_number_field(self) -> None:
        payload = self.client._number_query_payload("000123", "view-state")

        self.assertEqual(payload["consultarnfseForm:numNfse"], "000123")
        self.assertEqual(payload["consultarnfseForm:j_id237"], "consultarnfseForm:j_id237")
        self.assertNotIn("consultarnfseForm:dataInicialInputDate", payload)


class InferNfsePeriodTests(unittest.TestCase):
    def test_infers_month_from_issue_date(self) -> None:
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <CompNfse>
          <Nfse>
            <InfNfse>
              <DataEmissao>2026-06-09T10:30:00</DataEmissao>
            </InfNfse>
          </Nfse>
        </CompNfse>
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nota.xml"
            path.write_bytes(xml)

            period = infer_nfse_period(path)

        self.assertEqual(period.yyyymm, "202606")


if __name__ == "__main__":
    unittest.main()
