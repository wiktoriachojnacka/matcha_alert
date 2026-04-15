# Matcha Stock Monitor

A simple Python script that monitors online stores for ceremonial matcha
and sends an alert when a product is back in stock.

Monitored stores:
- [ouritsumatcha.pl](https://ouritsumatcha.pl/kategoria-produktu/herbaty/matcha/)
- [lunetea.pl](https://lunetea.pl/collections/matcha)
- [oromatcha.com](https://oromatcha.com/pl/menu/matcha-164.html)

## Installation

```bash
pip install requests beautifulsoup4
```

## Configuration

Open `matcha_monitor.py` and fill in at least one notification channel
(SMTP email, Telegram, or Discord webhook). Console logging is always on.

## Usage

```bash
python matcha_monitor.py
```

The script checks every 30 minutes. The first run records a baseline to
`matcha_state.json`; alerts only fire on the transition from **out of
stock** to **in stock**. Stop with `Ctrl+C`.

## Notes

- Filters products by the keywords `ceremonial` / `ceremony` in the name.
- Don't lower the interval below a few minutes - these are small shops.
- If a scraper starts returning nothing, the store's HTML has changed,
  update the selectors in the relevant `scrape_*` function.
