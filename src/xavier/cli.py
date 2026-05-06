from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from .config import load_env
from .models import Coupon, ValidationResult
from .monitor import run_monitor_sync
from .notifier import STATUS_LABELS_PT, format_summary, send_webhook
from .scrapers import ALL_SCRAPERS
from .state import DEFAULT_STATE_PATH, load_state
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
    load_env()


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


@cli.command()
@click.option("--webhook", envvar="XAVIER_WEBHOOK_URL", required=True,
              help="URL do webhook Google Chat (env XAVIER_WEBHOOK_URL)")
@click.option("--state", "state_path",
              type=click.Path(dir_okay=False, path_type=Path),
              default=DEFAULT_STATE_PATH, show_default=True)
@click.option("--phrases", "phrases_path",
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=Path("phrases.json"), show_default=True)
@click.option("--headless/--headed", default=True, show_default=True)
@click.option("--throttle", type=float, default=8.0, show_default=True,
              help="Segundos entre validações no ML")
@click.option("--max-candidates", type=int, default=10, show_default=True)
def monitor(webhook: str, state_path: Path, phrases_path: Path, headless: bool,
            throttle: float, max_candidates: int) -> None:
    """Roda 1 ciclo do monitor: lê /cupons/active, busca novos, testa, notifica.

    Idempotente: sem mudança = sem webhook.
    """
    result = run_monitor_sync(
        webhook_url=webhook,
        state_path=state_path,
        phrases_path=phrases_path,
        headless=headless,
        throttle_seconds=throttle,
        max_candidates=max_candidates,
    )
    console.log(result.summary)
    if result.sent_webhooks:
        console.log("[green]✓[/] webhooks enviados")
    else:
        console.log("[dim]sem mudança — rodada silenciosa[/]")


@cli.command()
def login() -> None:
    """Abre o Chromium em modo headed pra você logar no ML uma vez.

    Use isso quando o auto-login falhar por captcha ou 2FA. A sessão
    é salva em .playwright-state/ e o `xavier monitor` passa a usar.
    """
    import asyncio as _asyncio

    from playwright.async_api import async_playwright as _apw

    from .validator import STORAGE_STATE

    async def _go():
        STORAGE_STATE.parent.mkdir(parents=True, exist_ok=True)
        async with _apw() as pw:
            browser = await pw.chromium.launch(headless=False)
            ctx = await browser.new_context(
                locale="pt-BR",
                storage_state=str(STORAGE_STATE) if STORAGE_STATE.exists() else None,
            )
            page = await ctx.new_page()
            await page.goto("https://www.mercadolivre.com.br/")
            console.log(
                "[yellow]Faça login na janela aberta. Quando terminar, "
                "feche o navegador (X) que a sessão será salva.[/]"
            )
            try:
                await page.wait_for_event("close", timeout=0)
            except Exception:
                pass
            await ctx.storage_state(path=str(STORAGE_STATE))
            await browser.close()
        console.log(f"[green]✓[/] sessão salva em {STORAGE_STATE}")

    _asyncio.run(_go())


@cli.command(name="state-show")
@click.option("--state", "state_path",
              type=click.Path(dir_okay=False, path_type=Path),
              default=DEFAULT_STATE_PATH, show_default=True)
def state_show(state_path: Path) -> None:
    """Imprime o estado atual do monitor."""
    s = load_state(state_path)
    console.print_json(data=s.model_dump(mode="json"))


@cli.command(name="test-webhook")
@click.option("--webhook", envvar="XAVIER_WEBHOOK_URL", required=True,
              help="URL do webhook (default: env XAVIER_WEBHOOK_URL)")
def test_webhook(webhook: str) -> None:
    """Posta uma mensagem curta no webhook para validar a conexão."""
    import httpx
    payload = {"text": "Xavier — teste de webhook ✅"}
    resp = httpx.post(webhook, json=payload, timeout=10)
    if resp.status_code < 300:
        console.log(f"[green]✓[/] webhook OK ({resp.status_code})")
    else:
        console.log(f"[red]✗[/] webhook respondeu {resp.status_code}: {resp.text[:200]}")


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
