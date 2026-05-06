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

## Configuração do webhook

O resultado pode ser postado em um webhook (ex.: Google Chat, Slack incoming).
Configure a URL via variável de ambiente — **nunca commite a URL**, ela contém
uma chave/token de escrita.

```bash
cp .env.example .env
# edite .env e preencha XAVIER_WEBHOOK_URL=https://...
export $(grep -v '^#' .env | xargs)
xavier test-webhook   # ping rápido pra validar
```

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
