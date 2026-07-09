from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from nfs_fortaleza.config import DEFAULT_DOWNLOADS_DIR, load_settings
from nfs_fortaleza.load import load_nfse_xml
from nfs_fortaleza.periods import iter_date_windows, iter_months, looks_like_date, parse_date, parse_month_period
from nfs_fortaleza.portal import PeriodWithoutInvoicesError, PortalClient, PortalOptions


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

@app.command()
def run(
    competencia: CompetenciaOpt = None,
    inicio: InicioOpt = None,
    fim: FimOpt = None,
    downloads_dir: Annotated[Path, typer.Option("--downloads-dir")] = DEFAULT_DOWNLOADS_DIR,
) -> None:
    """Executa download do XML, leitura dos campos e carga no Postgres."""
    settings = load_settings()
    client = PortalClient(
        settings,
        PortalOptions(downloads_dir=downloads_dir),
    )

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
    downloads_dir: Annotated[Path, typer.Option("--downloads-dir")] = DEFAULT_DOWNLOADS_DIR,
) -> None:
    """Baixa XMLs sem carregar no banco."""
    settings = load_settings()
    client = PortalClient(
        settings,
        PortalOptions(downloads_dir=downloads_dir),
    )
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
