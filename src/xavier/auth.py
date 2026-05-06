"""Login automatizado no Mercado Livre.

Importante:
  - As credenciais vêm de XAVIER_ML_EMAIL / XAVIER_ML_PASSWORD (env / .env).
  - Nunca logamos a senha. Em logs aparece só o email mascarado.
  - Captcha/2FA quebra o login automatizado — nesses casos retornamos
    um resultado específico para o monitor mandar webhook avisando.
"""
from __future__ import annotations

import asyncio
import logging
import re
from enum import Enum

from playwright.async_api import (
    Page,
    TimeoutError as PlaywrightTimeout,
)

log = logging.getLogger(__name__)

LOGIN_URL = "https://www.mercadolivre.com.br/jms/mlb/lgz/login"
HOME_URL = "https://www.mercadolivre.com.br/"


class LoginOutcome(str, Enum):
    SUCCESS = "success"
    ALREADY_LOGGED_IN = "already_logged_in"
    INVALID_CREDENTIALS = "invalid_credentials"
    CAPTCHA = "captcha"
    TWO_FACTOR = "two_factor"
    UNKNOWN = "unknown"


def _mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"{local[0]}*@{domain}"
    return f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}@{domain}"


async def is_logged_in(page: Page) -> bool:
    """Heurística: o ML expõe um link 'Crie sua conta' / 'Entre' quando deslogado."""
    try:
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=15000)
    except PlaywrightTimeout:
        return False
    if "registration" in page.url or "login" in page.url:
        return False
    login_link = page.locator(
        "a[href*='registration'], a:has-text('Crie sua conta'), a:has-text('Entre')"
    ).first
    return await login_link.count() == 0 or not await login_link.is_visible()


async def attempt_ml_login(page: Page, email: str, password: str) -> LoginOutcome:
    """Tenta logar no ML programaticamente.

    Fluxo (pode mudar conforme o ML atualiza):
      1. /jms/mlb/lgz/login → input de e-mail → botão Continuar
      2. próxima tela → input de senha → Entrar
      3. ou captcha/2fa → desistir e devolver outcome específico
    """
    if await is_logged_in(page):
        return LoginOutcome.ALREADY_LOGGED_IN

    log.info("login automatizado para %s", _mask_email(email))

    try:
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
    except PlaywrightTimeout:
        log.warning("timeout abrindo login do ML")
        return LoginOutcome.UNKNOWN

    if await _has_captcha(page):
        return LoginOutcome.CAPTCHA

    # Etapa 1: e-mail
    email_input = page.locator(
        "input[name='user_id'], input[name='email'], input[type='email'], input#user_id"
    ).first
    if await email_input.count() == 0:
        log.warning("campo de email não encontrado")
        return LoginOutcome.UNKNOWN

    await email_input.fill(email)
    await _click_continue(page)
    await _settle(page)

    if await _has_captcha(page):
        return LoginOutcome.CAPTCHA
    if await _two_factor_required(page):
        return LoginOutcome.TWO_FACTOR

    # Etapa 2: senha (pode estar na mesma página ou em outra)
    pw_input = page.locator("input[name='password'], input[type='password']").first
    if await pw_input.count() == 0:
        # Em alguns fluxos o ML pede só email + magic link / SMS
        return LoginOutcome.TWO_FACTOR

    await pw_input.fill(password)
    await _click_continue(page)
    await _settle(page)

    if await _has_captcha(page):
        return LoginOutcome.CAPTCHA
    if await _two_factor_required(page):
        return LoginOutcome.TWO_FACTOR
    if await _invalid_credentials(page):
        return LoginOutcome.INVALID_CREDENTIALS

    # Espera pequeno tempo e verifica resultado
    await asyncio.sleep(2.0)
    if await is_logged_in(page):
        return LoginOutcome.SUCCESS
    return LoginOutcome.UNKNOWN


async def _click_continue(page: Page) -> None:
    btn = page.locator(
        "button:has-text('Continuar'), "
        "button:has-text('Entrar'), "
        "button[type='submit']"
    ).first
    if await btn.count() > 0:
        try:
            await btn.click(timeout=4000)
            return
        except PlaywrightTimeout:
            pass
    # Fallback: Enter
    await page.keyboard.press("Enter")


async def _settle(page: Page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except PlaywrightTimeout:
        pass
    await asyncio.sleep(1.0)


async def _has_captcha(page: Page) -> bool:
    html = (await page.content()).lower()
    return (
        "captcha" in html
        or "verifique que você é humano" in html
        or "/security-challenge" in page.url
    )


async def _two_factor_required(page: Page) -> bool:
    html = (await page.content()).lower()
    markers = [
        "código de verificação",
        "codigo de verificacao",
        "enviamos um código",
        "verificação em duas etapas",
        "verificacao em duas etapas",
        "confirme que é você",
        "two-factor",
    ]
    return any(m in html for m in markers)


async def _invalid_credentials(page: Page) -> bool:
    html = (await page.content()).lower()
    markers = [
        "senha incorreta",
        "e-mail ou senha",
        "email ou senha",
        "credenciais inválidas",
        "credenciais invalidas",
        "não foi possível entrar",
    ]
    return any(m in html for m in markers)
