from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from nfs_fortaleza.config import DEFAULT_DOWNLOADS_DIR, PROJECT_ROOT, load_settings
from nfs_fortaleza.issuance import (
    ISSUER_CNPJ,
    IssuanceLedger,
    NfseIssuanceClient,
    filter_unissued_rows,
)
from nfs_fortaleza.load import load_nfse_xml
from nfs_fortaleza.nfse_xml import infer_nfse_period
from nfs_fortaleza.periods import iter_date_windows, iter_months, looks_like_date, parse_date, parse_month_period
from nfs_fortaleza.portal import PeriodWithoutInvoicesError, PortalClient, PortalOptions
from nfs_fortaleza.spreadsheet import load_invoice_rows, select_rows


app = typer.Typer(help="Baixa XML de NFS-e Fortaleza e carrega os campos no Postgres via dlt.")
console = Console()


CompetenciaOpt = Annotated[
    str | None,
    typer.Option("--competencia", "-c", help="Competencia unica: 06/2026, 2026-06 ou Junho, 2026."),
]
InicioOpt = Annotated[
    str | None,
    typer.Option("--inicio", help="Primeira competencia ou data, ex.: 01/2026 ou 01/06/2026."),
]
FimOpt = Annotated[
    str | None,
    typer.Option("--fim", help="Ultima competencia ou data, ex.: 06/2026 ou 09/07/2026."),
]
CnpjOpt = Annotated[
    str | None,
    typer.Option("--cnpj", help="CNPJ da inscricao que emitiu a NFS-e."),
]
NumeroNfseOpt = Annotated[
    str | None,
    typer.Option("--numero-nfse", help="Numero da NFS-e, com ate 15 digitos."),
]

@app.command()
def run(
    competencia: CompetenciaOpt = None,
    inicio: InicioOpt = None,
    fim: FimOpt = None,
    cnpj: CnpjOpt = None,
    numero_nfse: NumeroNfseOpt = None,
    downloads_dir: Annotated[Path, typer.Option("--downloads-dir")] = DEFAULT_DOWNLOADS_DIR,
) -> None:
    """Executa download do XML, leitura dos campos e carga no Postgres."""
    nfse_query = _resolve_nfse_query(cnpj, numero_nfse, competencia, inicio, fim)
    settings = load_settings()
    client = PortalClient(
        settings,
        PortalOptions(downloads_dir=downloads_dir),
    )

    if nfse_query:
        query_cnpj, query_numero = nfse_query
        console.print(f"[bold]Processando NFS-e {query_numero} do CNPJ {query_cnpj}[/bold]")
        try:
            file_paths = client.export_nfse(query_cnpj, query_numero)
        except PeriodWithoutInvoicesError as exc:
            console.print(f"[yellow]Ignorado:[/yellow] {exc}")
            return
        for file_path in file_paths:
            console.print(f"XML baixado: {file_path}")
            period = infer_nfse_period(file_path)
            console.print(f"Competencia identificada no XML: {period.label}")
            load_info = load_nfse_xml(settings, file_path, period)
            console.print(load_info)
        return

    for period in _resolve_periods(competencia, inicio, fim):
        console.print(f"[bold]Processando periodo {period.label}[/bold]")
        try:
            file_paths = client.export_competencia(period)
        except PeriodWithoutInvoicesError as exc:
            console.print(f"[yellow]Ignorado:[/yellow] {exc}")
            continue
        for file_path in file_paths:
            console.print(f"XML baixado: {file_path}")
            load_info = load_nfse_xml(settings, file_path, period)
            console.print(load_info)


@app.command()
def download(
    competencia: CompetenciaOpt = None,
    inicio: InicioOpt = None,
    fim: FimOpt = None,
    cnpj: CnpjOpt = None,
    numero_nfse: NumeroNfseOpt = None,
    downloads_dir: Annotated[Path, typer.Option("--downloads-dir")] = DEFAULT_DOWNLOADS_DIR,
) -> None:
    """Baixa XMLs sem carregar no banco."""
    nfse_query = _resolve_nfse_query(cnpj, numero_nfse, competencia, inicio, fim)
    settings = load_settings()
    client = PortalClient(
        settings,
        PortalOptions(downloads_dir=downloads_dir),
    )
    if nfse_query:
        query_cnpj, query_numero = nfse_query
        console.print(f"[bold]Processando NFS-e {query_numero} do CNPJ {query_cnpj}[/bold]")
        try:
            file_paths = client.export_nfse(query_cnpj, query_numero)
        except PeriodWithoutInvoicesError as exc:
            console.print(f"[yellow]Ignorado:[/yellow] {exc}")
            return
        for file_path in file_paths:
            console.print(f"XML baixado: {file_path}")
        return

    for period in _resolve_periods(competencia, inicio, fim):
        console.print(f"[bold]Processando periodo {period.label}[/bold]")
        try:
            file_paths = client.export_competencia(period)
        except PeriodWithoutInvoicesError as exc:
            console.print(f"[yellow]Ignorado:[/yellow] {exc}")
            continue
        for file_path in file_paths:
            console.print(f"XML baixado: {file_path}")


@app.command("load-file")
def load_file(
    file_path: Annotated[Path, typer.Argument(help="Caminho do XML/ZIP gerado pelo portal.")],
    competencia: Annotated[str, typer.Option("--competencia", "-c", help="Competencia do arquivo: 06/2026.")],
) -> None:
    """Carrega no Postgres os campos de um XML/ZIP ja baixado."""
    settings = load_settings()
    period = _parse_month_parameter(competencia, "--competencia")
    load_info = load_nfse_xml(settings, file_path, period)
    console.print(load_info)


@app.command("emitir-planilha")
def emitir_planilha(
    planilha: Annotated[
        Path,
        typer.Argument(help="Planilha XLSX com os clientes e valores das NFS-e."),
    ] = PROJECT_ROOT / "NOTAS FISCAIS.xlsx",
    linha: Annotated[
        int | None,
        typer.Option("--linha", help="Numero da linha da planilha a processar, incluindo o cabecalho."),
    ] = None,
    todas: Annotated[
        bool,
        typer.Option("--todas", help="Processa todas as linhas ainda nao registradas no historico local."),
    ] = False,
    limite: Annotated[
        int | None,
        typer.Option("--limite", help="Limite de linhas quando --todas for usado."),
    ] = None,
    confirmar_emissao: Annotated[
        bool,
        typer.Option(
            "--confirmar-emissao",
            help="Autoriza validar, confirmar e efetivamente emitir as notas no portal.",
        ),
    ] = False,
    cnpj: Annotated[
        str,
        typer.Option("--cnpj", help="CNPJ da inscricao emissora."),
    ] = ISSUER_CNPJ,
    downloads_dir: Annotated[Path, typer.Option("--downloads-dir")] = DEFAULT_DOWNLOADS_DIR,
) -> None:
    """Valida a planilha e, com confirmacao explicita, emite NFS-e por requests HTTP."""
    try:
        rows = load_invoice_rows(planilha)
        selected = select_rows(rows, row_number=linha, all_rows=todas, limit=limite)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc), param_hint="planilha/--linha/--todas") from exc

    ledger = IssuanceLedger(downloads_dir / "emissoes_nfse.jsonl")
    pending, skipped = filter_unissued_rows(selected, ledger)
    for row in skipped:
        console.print(
            f"[yellow]Ignorada linha {row.row_number}:[/yellow] ja consta como emitida no historico local."
        )

    table = Table(title="NFS-e selecionadas")
    table.add_column("Linha", justify="right")
    table.add_column("Paciente")
    table.add_column("CPF")
    table.add_column("Exame")
    table.add_column("Valor", justify="right")
    for row in pending:
        table.add_row(
            str(row.row_number),
            row.paciente,
            row.cpf_formatted,
            row.tipo_exame,
            f"R$ {row.valor_br}",
        )
    console.print(table)

    if not pending:
        console.print("[yellow]Nenhuma linha pendente para emissao.[/yellow]")
        return
    if not confirmar_emissao:
        console.print(
            "[cyan]Previa concluida sem alterar o portal.[/cyan] "
            "Use --confirmar-emissao para autorizar a emissao."
        )
        return

    normalized_cnpj = re.sub(r"\D", "", cnpj)
    if len(normalized_cnpj) != 14:
        raise typer.BadParameter("CNPJ invalido: informe os 14 digitos.", param_hint="--cnpj")

    settings = load_settings()
    client = NfseIssuanceClient(
        settings,
        PortalOptions(downloads_dir=downloads_dir),
    )
    for row in pending:
        console.print(f"[bold]Emitindo linha {row.row_number}: {row.paciente}[/bold]")
        result = client.issue(row, cnpj=normalized_cnpj)
        ledger.record_success(row, result)
        registration = "cliente cadastrado" if result.client_registered else "cliente ja existente"
        console.print(
            f"[green]NFS-e {result.numero_nfse} emitida ({registration}).[/green] "
            f"PDF: {result.pdf_path}"
        )


def _resolve_nfse_query(
    cnpj: str | None,
    numero_nfse: str | None,
    competencia: str | None,
    inicio: str | None,
    fim: str | None,
) -> tuple[str, str] | None:
    if cnpj is None and numero_nfse is None:
        return None
    if not cnpj or not numero_nfse:
        raise typer.BadParameter(
            "Informe --cnpj e --numero-nfse juntos.",
            param_hint="--cnpj/--numero-nfse",
        )
    if competencia or inicio or fim:
        raise typer.BadParameter(
            "Use --cnpj/--numero-nfse ou os filtros de competencia/periodo, nao ambos.",
            param_hint="--cnpj/--numero-nfse",
        )

    raw_cnpj = cnpj.strip()
    if not re.fullmatch(r"[\d.\-/\s]+", raw_cnpj):
        raise typer.BadParameter("CNPJ invalido: use apenas numeros ou a formatacao padrao.", param_hint="--cnpj")
    normalized_cnpj = re.sub(r"\D", "", raw_cnpj)
    if len(normalized_cnpj) != 14:
        raise typer.BadParameter("CNPJ invalido: informe os 14 digitos.", param_hint="--cnpj")

    normalized_numero = numero_nfse.strip()
    if not normalized_numero.isdigit() or len(normalized_numero) > 15:
        raise typer.BadParameter(
            "Numero da NFS-e invalido: informe de 1 a 15 digitos.",
            param_hint="--numero-nfse",
        )
    return normalized_cnpj, normalized_numero


def _resolve_periods(competencia: str | None, inicio: str | None, fim: str | None):
    if competencia:
        if inicio or fim:
            raise typer.BadParameter("Use --competencia ou --inicio/--fim, nao ambos.")
        return [_parse_month_parameter(competencia, "--competencia")]

    if not inicio or not fim:
        raise typer.BadParameter("Informe --competencia ou o par --inicio e --fim.")

    if looks_like_date(inicio) or looks_like_date(fim):
        if not (looks_like_date(inicio) and looks_like_date(fim)):
            raise typer.BadParameter("Quando usar datas, --inicio e --fim devem ser datas completas.")
        start_date = _parse_date_parameter(inicio, "--inicio")
        end_date = _parse_date_parameter(fim, "--fim")
        if end_date < start_date:
            raise typer.BadParameter("--fim deve ser maior ou igual a --inicio.")
        windows = list(iter_date_windows(start_date, end_date))
        if not windows:
            raise typer.BadParameter("--inicio esta no futuro; nao ha periodo consultavel.")
        return windows

    start = _parse_month_parameter(inicio, "--inicio")
    end = _parse_month_parameter(fim, "--fim")
    if end < start:
        raise typer.BadParameter("--fim deve ser maior ou igual a --inicio.")
    return list(iter_months(start, end))


def _parse_month_parameter(value: str, option_name: str):
    try:
        return parse_month_period(value)
    except ValueError as exc:
        raise typer.BadParameter(
            f"{option_name} invalido: {value!r}. Use uma competencia como 07/2026, 2026-07 ou Julho, 2026."
        ) from exc


def _parse_date_parameter(value: str, option_name: str):
    try:
        return parse_date(value)
    except ValueError as exc:
        raise typer.BadParameter(
            f"{option_name} invalido: {value!r}. Use uma data como 01/07/2026 ou 2026-07-01."
        ) from exc


if __name__ == "__main__":
    app()
