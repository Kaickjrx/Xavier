from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from .models import Coupon, ValidationResult
from .notifier import STATUS_LABELS_PT, format_summary, send_webhook
from .scrapers import ALL_SCRAPERS
from .storage import deduplicate, load_coupons, save_coupons, save_results
from .validator import MercadoLivreValidator

console = Console()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )


def _scrape_all() -> list[Coupon]:
    coupons: list[Coupon] = []
    for cls in ALL_SCRAPERS:
        with cls() as scraper:
            console.log(f"[cyan]→[/] coletando de [bold]{scraper.name}[/]")
            found = scraper.fetch()
            console.log(f"  encontrados: {len(found)}")
            coupons.extend(found)
    coupons = deduplicate(coupons)
    return coupons


def _print_coupons(coupons: list[Coupon]) -> None:
    table = Table(title=f"Cupons coletados ({len(coupons)})")
    table.add_column("Código", style="bold")
    table.add_column("Desconto")
    table.add_column("Descrição")
    table.add_column("Fonte", style="dim")
    for c in coupons:
        table.add_row(c.code, c.discount or "-", c.description or "-", c.source)
    console.print(table)


def _print_results(results: list[ValidationResult]) -> None:
    table = Table(title=f"Resultado da validação ({len(results)})")
    table.add_column("Código", style="bold")
    table.add_column("Status")
    table.add_column("Mensagem", overflow="fold")
    for r in results:
        table.add_row(
            r.coupon.code,
            STATUS_LABELS_PT.get(r.status, r.status.value),
            r.message or "",
        )
    console.print(table)


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Logs em DEBUG")
def cli(verbose: bool) -> None:
    """Xavier — extrai e valida cupons do Mercado Livre."""
    _setup_logging(verbose)


@cli.command()
@click.option(
    "-o", "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("coupons.json"),
    show_default=True,
)
def scrape(output: Path) -> None:
    """Coleta cupons das fontes configuradas."""
    coupons = _scrape_all()
    save_coupons(coupons, output)
    _print_coupons(coupons)
    console.log(f"[green]✓[/] {len(coupons)} cupons salvos em {output}")


@cli.command()
@click.argument("coupons_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "-o", "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("results.json"),
    show_default=True,
)
@click.option("--headless", is_flag=True, help="Roda Playwright sem abrir janela")
@click.option("--throttle", type=float, default=12.0, show_default=True,
              help="Segundos entre validações (jitter aplicado em cima)")
@click.option("--webhook", envvar="XAVIER_WEBHOOK_URL",
              help="URL para POST do resumo (default: env XAVIER_WEBHOOK_URL)")
def validate(coupons_file: Path, output: Path, headless: bool, throttle: float,
             webhook: str | None) -> None:
    """Aplica cada cupom em ML > Cupons e classifica o resultado."""
    coupons = load_coupons(coupons_file)
    if not coupons:
        console.log("[yellow]nenhum cupom para validar[/]")
        return

    validator = MercadoLivreValidator(headless=headless, throttle_seconds=throttle)
    results = asyncio.run(validator.validate_all(coupons))
    save_results(results, output)
    _print_results(results)
    console.log(f"[green]✓[/] resultados salvos em {output}")

    if webhook:
        try:
            send_webhook(webhook, results)
            console.log("[green]✓[/] webhook enviado")
        except Exception as exc:
            console.log(f"[red]✗[/] erro ao enviar webhook: {exc}")
    else:
        console.print("\n[dim]Sem webhook configurado. Resumo:[/]")
        console.print(format_summary(results))


@cli.command()
@click.option("-o", "--output",
              type=click.Path(dir_okay=False, path_type=Path),
              default=Path("results.json"),
              show_default=True)
@click.option("--coupons-out",
              type=click.Path(dir_okay=False, path_type=Path),
              default=Path("coupons.json"),
              show_default=True)
@click.option("--headless", is_flag=True)
@click.option("--throttle", type=float, default=12.0, show_default=True)
@click.option("--webhook", envvar="XAVIER_WEBHOOK_URL")
def run(output: Path, coupons_out: Path, headless: bool, throttle: float,
        webhook: str | None) -> None:
    """Pipeline completo: scrape → validate → (webhook)."""
    coupons = _scrape_all()
    save_coupons(coupons, coupons_out)
    _print_coupons(coupons)
    if not coupons:
        console.log("[yellow]nenhum cupom coletado, abortando[/]")
        return

    validator = MercadoLivreValidator(headless=headless, throttle_seconds=throttle)
    results = asyncio.run(validator.validate_all(coupons))
    save_results(results, output)
    _print_results(results)

    if webhook:
        try:
            send_webhook(webhook, results)
            console.log("[green]✓[/] webhook enviado")
        except Exception as exc:
            console.log(f"[red]✗[/] erro ao enviar webhook: {exc}")
    else:
        console.print("\n[dim]Sem webhook (defina XAVIER_WEBHOOK_URL ou use --webhook). Resumo:[/]")
        console.print(format_summary(results))


@cli.command(name="format-preview")
@click.argument("results_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def format_preview(results_file: Path) -> None:
    """Imprime como ficaria o payload do webhook (sem enviar)."""
    import json
    raw = json.loads(results_file.read_text(encoding="utf-8"))
    results = [ValidationResult.model_validate(r) for r in raw]
    console.print(format_summary(results))


if __name__ == "__main__":
    cli()
