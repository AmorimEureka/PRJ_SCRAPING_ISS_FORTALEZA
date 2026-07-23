from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from nfs_fortaleza.issuance import (
    IssuanceLedger,
    IssuanceResult,
    _extract_direct_form_state,
    _extract_invoice_number,
    _extract_pdf_url,
    _find_suggestion_selection_action,
    _script_action_ids,
    _select_option_value,
    _suggestion_selection_value,
    filter_unissued_rows,
)
from nfs_fortaleza.spreadsheet import (
    InvoiceSpreadsheetRow,
    is_valid_cpf,
    load_invoice_rows,
    select_rows,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def example_row() -> InvoiceSpreadsheetRow:
    return InvoiceSpreadsheetRow(
        row_number=2,
        paciente="ANTONIO ÍRIS DE FREITAS",
        local="CLINICA 2",
        tipo_atendimento="AMBULATORIO",
        atendimento="317189",
        cpf="155.061.423-15",
        valor=Decimal("60.75"),
        rua="rua Alameda rosa Maria",
        numero_casa="219",
        bairro="cidade 2000",
        cidade="FORTALEZA",
        uf="CE",
        tipo_exame="ANÁLISE CLÍNICA",
        data="2026-05-13 00:00:00",
        email="",
    )


class SpreadsheetTests(unittest.TestCase):
    def test_loads_reference_first_row(self) -> None:
        rows = load_invoice_rows(PROJECT_ROOT / "NOTAS FISCAIS.xlsx")

        self.assertGreater(len(rows), 300)
        self.assertEqual(rows[0], example_row())
        self.assertEqual(rows[0].valor_br, "60,75")

    def test_validates_cpf_check_digits(self) -> None:
        self.assertTrue(is_valid_cpf("155.061.423-15"))
        self.assertFalse(is_valid_cpf("155.061.423-16"))
        self.assertFalse(is_valid_cpf("111.111.111-11"))

    def test_requires_explicit_row_or_all(self) -> None:
        with self.assertRaises(ValueError):
            select_rows([example_row()], row_number=None, all_rows=False, limit=None)

    def test_builds_required_pdf_name(self) -> None:
        self.assertEqual(
            example_row().pdf_filename("8"),
            "8 - CLINICA 2, AMBULATORIO e ANTONIO ÍRIS DE FREITAS.pdf",
        )


class JsfParserTests(unittest.TestCase):
    def test_extracts_only_direct_controls_from_main_form(self) -> None:
        html = """
        <form id="emitirnfseForm">
          <input type="hidden" name="emitirnfseForm" value="emitirnfseForm" />
          <input name="emitirnfseForm:idNome" value="Maria" />
          <input name="emitirnfseForm:idFormularioPesquisaCnae:idCnaePesquisa" value="8610101" />
          <select name="emitirnfseForm:comboEscolherNbs">
            <option value="">...</option>
            <option value="476" selected="selected">123011900 - SERVIÇOS HOSPITALARES</option>
          </select>
          <input type="hidden" name="javax.faces.ViewState" value="state-1" />
        </form>
        """

        state = _extract_direct_form_state(html, "emitirnfseForm")

        self.assertEqual(state["emitirnfseForm"], "emitirnfseForm")
        self.assertEqual(state["emitirnfseForm:idNome"], "Maria")
        self.assertEqual(state["emitirnfseForm:comboEscolherNbs"], "476")
        self.assertNotIn("emitirnfseForm:idFormularioPesquisaCnae:idCnaePesquisa", state)

    def test_finds_option_by_portal_label_prefix(self) -> None:
        html = """
        <select name="emitirnfseForm:comboEscolherNbs">
          <option value="475">123011500 - OUTROS</option>
          <option value="476">123011900 - SERVIÇOS HOSPITALARES</option>
        </select>
        """

        self.assertEqual(
            _select_option_value(
                html,
                "emitirnfseForm:comboEscolherNbs",
                "123011900",
                prefix=True,
            ),
            "476",
        )

    def test_extracts_jsf_actions_in_execution_order(self) -> None:
        script = """
        A4J.AJAX.Submit('emitirnfseForm',event,
          {'parameters':{'emitirnfseForm:j_id861':'emitirnfseForm:j_id861'}});
        A4J.AJAX.Submit('emitirnfseForm',event,
          {'parameters':{'emitirnfseForm:btnCalcular':'emitirnfseForm:btnCalcular'}});
        """

        self.assertEqual(
            _script_action_ids(script),
            ["emitirnfseForm:j_id861", "emitirnfseForm:btnCalcular"],
        )

    def test_extracts_success_number_and_pdf_endpoint(self) -> None:
        html = """
        <label>Número da Nota:</label><input value="8" />
        <object data="/grpfor/a4j/s/3_3_3.FinalResource.pdf"></object>
        """

        self.assertEqual(_extract_invoice_number(html), "8")
        self.assertEqual(
            _extract_pdf_url(html, "https://iss.example/grpfor/pages/sucesso.seam?cid=1"),
            "https://iss.example/grpfor/a4j/s/3_3_3.FinalResource.pdf",
        )

    def test_uses_richfaces_row_index_and_exact_onselect_action(self) -> None:
        html = """
        <script>
        new RichFaces.Suggestion(
          'emitirnfseForm','emitirnfseForm:cpfPesquisaTomador','emitirnfseForm:j_id216',
          {'onselect':function(suggestion,event){
            A4J.AJAX.Submit('emitirnfseForm',event,{
              'parameters':{
                'emitirnfseForm:j_id216:j_id223':'emitirnfseForm:j_id216:j_id223'
              }
            })
          }}
        );
        </script>
        <table>
          <tr class="richfaces_suggestionEntry">
            <td style="display:none">15506142315</td>
            <td>ANTONIO ÍRIS DE FREITAS</td>
          </tr>
          <tr><td>
            <input onclick="'emitirnfseForm:j_id265':'emitirnfseForm:j_id265'" />
          </td></tr>
        </table>
        """

        self.assertEqual(_suggestion_selection_value(html, example_row()), "0")
        self.assertEqual(
            _find_suggestion_selection_action(html, "emitirnfseForm:j_id216"),
            "emitirnfseForm:j_id216:j_id223",
        )


class LedgerTests(unittest.TestCase):
    def test_prevents_reissuing_a_successful_row(self) -> None:
        row = example_row()
        with tempfile.TemporaryDirectory() as directory:
            ledger = IssuanceLedger(Path(directory) / "ledger.jsonl")
            result = IssuanceResult(2, "8", Path(directory) / row.pdf_filename("8"), row.paciente, row.cpf, True)
            ledger.record_success(row, result)

            pending, skipped = filter_unissued_rows([row], ledger)

        self.assertEqual(pending, [])
        self.assertEqual(skipped, [row])


if __name__ == "__main__":
    unittest.main()
