# Xavier — Extrator e validador de cupons do Mercado Livre

Ferramenta em Python que:

1. **Busca** cupons do Mercado Livre em sites agregadores públicos (Cuponomia, CupomValido, etc.)
2. **Valida** os cupons coletados aplicando-os em uma sessão autenticada no `mercadolivre.com.br` via Playwright
3. **Reporta** quais estão ativos, expirados ou inválidos

## Aviso importante

- Este projeto faz scraping de sites públicos de agregadores de cupom. Verifique o `robots.txt` e os Termos de Uso de cada fonte antes de rodar em escala.
- A validação no Mercado Livre **requer login do usuário** (a sessão é sua, autenticada manualmente na primeira execução). O script não tenta burlar captchas, MFA ou rate limiting do ML.
- Use com moderação. Há um throttle padrão de 5s entre validações para evitar sobrecarga.

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
```

## Configuração

Copie o `.env.example` para `.env` (gitignored) e preencha:

```bash
cp .env.example .env
```

```ini
XAVIER_WEBHOOK_URL=https://chat.googleapis.com/...
XAVIER_ML_EMAIL=seu.email@dominio.com
XAVIER_ML_PASSWORD=sua-senha
```

A CLI carrega o `.env` automaticamente (via `python-dotenv`) — não precisa
`export`. **Nunca commite o `.env`**: contém o webhook (chave/token) e a senha
do ML. O `.gitignore` já protege.

### Login no Mercado Livre

O monitor tenta logar **automaticamente** com `XAVIER_ML_EMAIL` /
`XAVIER_ML_PASSWORD` quando a sessão expira. Em dois cenários o auto-login
falha por design (proteção do ML):

- **Captcha** → o monitor manda webhook `[ml-cupons-monitor] Falha: captcha…`
  e aborta. Resolva manualmente com `xavier login` (abre janela headed).
- **2FA / verificação por SMS** → idem. Use `xavier login` uma vez para
  passar pelo desafio; a sessão fica salva em `.playwright-state/` e o
  monitor volta a rodar headless.

```bash
xavier login        # uma vez (ou quando der captcha/2FA)
xavier test-webhook # ping de sanidade no Google Chat
```

A senha **nunca** é logada — o código mascara o e-mail (`k****x@...`) e nunca
imprime a senha em stdout/stderr ou no state.

## Uso

```bash
# 1. Coletar cupons das fontes configuradas
xavier scrape --output coupons.json

# 2. Validar os cupons no Mercado Livre (abre navegador, pede login na 1ª vez)
xavier validate coupons.json --output results.json

# 3. Pipeline completo (scrape + validate + webhook)
xavier run --output results.json

# 4. Pré-visualizar formato do webhook sem enviar
xavier format-preview results.json
```

Cada cupom é postado no webhook como uma linha:

```
CODIGO | DESCRIÇÃO | Status
```

## Modo monitor (fluxo automático)

`xavier monitor` é o ciclo idempotente baseado no spec do feedback memory:

1. Lê `https://www.mercadolivre.com.br/cupons/active` (sessão logada via Playwright)
2. Faz diff vs `state/ml-cupons-state.json`: NEWLY_ACTIVE, NEWLY_EXPIRED
3. Coleta candidatos de fontes externas em ordem de prioridade:
   AdoroCupom → ValePlus → Promobit → Méliuz → Cuponomia → CupomValido
   (cupons com badge "verificado há +3 dias" ou "expirado" são descartados)
4. Testa cada candidato no modal de cupom do ML, com 8s + jitter entre tentativas.
   Abandona uma fonte após 5 cupons inválidos/expirados na mesma rodada.
5. Re-lê `/cupons/active` pra confirmar quem realmente entrou (modal limpo ≠ aceito).
6. Se houve mudança, dispara **2 webhooks** (mensagens separadas) no Google Chat:

   **Webhook 2** (lista):
   ```
   CUPONS ativos:
   COD1 | COD2 | COD3
   São N novos.

   CUPONS expirados:
   COD_X | COD_Y
   ```

   **Webhook 3** (detalhado):
   ```
   *FRASE EM CAIXA ALTA* 🚀

   🎟️ *COD1* - descrição
   🎟️ *COD2* - descrição - (NOVO)

   Ative o cupom no link pelo app: https://meli.la/25EE8mV

   🔗 Convide um amigo(a) para o grupo: https://chat.whatsapp.com/...
   ```

7. Atualiza `state/ml-cupons-state.json` (active, announced_codes,
   tested_dead_count, recent_phrases, last_run).
8. Se não houve mudança: rodada silenciosa, só `last_run` é atualizado.

### Banco de frases

Edite `phrases.json` (raiz do repo) com a lista de frases que rotacionam na
linha 1 do Webhook 3. O monitor evita repetir as 6 últimas usadas
(salvas em `state.recent_phrases`).

### Falhas

Em qualquer falha (browser indisponível, sessão expirada, captcha) o monitor
dispara **um único webhook curto** `[ml-cupons-monitor] Falha: <motivo>`
e aborta. Idempotência garantida — rodar 2x sem mudança não duplica nada.

### Comandos auxiliares

```bash
xavier state-show          # imprime o state atual
xavier test-webhook        # ping rápido no Google Chat
```

### Agendar (cron)

```cron
*/30 * * * * cd /caminho/Xavier && /caminho/Xavier/.venv/bin/xavier monitor --webhook "$XAVIER_WEBHOOK_URL" >> monitor.log 2>&1
```

## Estrutura

```
src/xavier/
├── cli.py             # Entry point (Click)
├── models.py          # Coupon dataclass
├── scrapers/
│   ├── base.py        # Interface Scraper
│   ├── cuponomia.py   # Implementação para cuponomia.com.br
│   └── cupomvalido.py # Implementação para cupomvalido.com.br
├── validator.py       # Validação via Playwright no ML
└── storage.py         # Carrega/salva JSON
```

## Como adicionar uma nova fonte

1. Crie `src/xavier/scrapers/minha_fonte.py` herdando de `Scraper`
2. Implemente o método `fetch() -> list[Coupon]`
3. Registre em `src/xavier/scrapers/__init__.py`

## Limitações conhecidas

- Os seletores CSS dos scrapers estão sujeitos a quebrar quando os sites de origem atualizam o layout. Ajuste em `scrapers/<fonte>.py`.
- A validação real só funciona com itens no carrinho. O validador detecta automaticamente se o carrinho está vazio e instrui o usuário a adicionar um produto barato antes.
- Cupons restritos a categorias/vendedores específicos podem ser reportados como inválidos mesmo estando ativos.
