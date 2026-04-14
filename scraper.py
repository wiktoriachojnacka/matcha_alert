"""
Ceremonial Matcha Stock Monitor
Monitors online stores for matcha availability and alerts on restocks.
"""

import json
import logging
import re
import smtplib
import time
from dataclasses import dataclass, asdict
from email.mime.text import MIMEText
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


STATE_FILE = Path("matcha_state.json")
CHECK_INTERVAL_SECONDS = 60 * 30  # 30 minutes
REQUEST_TIMEOUT = 20
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

CEREMONIAL_KEYWORDS = [
    "ceremonial", "ceremonialn",  # PL: "ceremonialna"
    "ceremony",
]


NOTIFY_CONSOLE = True            # always log to stdout

# Email (SMTP) leave SMTP_HOST empty to disable
SMTP_HOST = ""
SMTP_PORT = 587
SMTP_USER = ""
SMTP_PASS = ""
EMAIL_FROM = ""
EMAIL_TO = ""

# from @BotFather
TELEGRAM_TOKEN = ""
# your chat id
TELEGRAM_CHAT_ID = ""

DISCORD_WEBHOOK_URL = ""


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("matcha")


@dataclass(frozen=True)
class Product:
    store: str
    name: str
    url: str
    in_stock: bool
    price: str = ""

    def key(self) -> str:
        return f"{self.store}::{self.url}"


def fetch(url: str) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "pl,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    }
    resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def is_ceremonial(name: str) -> bool:
    low = name.lower()
    return any(k in low for k in CEREMONIAL_KEYWORDS)


def scrape_ouritsumatcha() -> list[Product]:
    """WooCommerce store: https://ouritsumatcha.pl"""
    url = "https://ouritsumatcha.pl/kategoria-produktu/herbaty/matcha/"
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    products: list[Product] = []

    for li in soup.select("li.product"):
        a = li.select_one(
            "a.woocommerce-LoopProduct-link") or li.select_one("a")
        name_el = li.select_one(
            ".woocommerce-loop-product__title") or li.select_one("h2")
        price_el = li.select_one(".price")
        if not a or not name_el:
            continue

        name = name_el.get_text(strip=True)
        href = urljoin(url, a.get("href", ""))
        price = price_el.get_text(" ", strip=True) if price_el else ""

        classes = " ".join(li.get("class", []))
        out_of_stock = "outofstock" in classes
        text = li.get_text(" ", strip=True).lower()
        if "wyczerpany" in text or "out of stock" in text:
            out_of_stock = True

        products.append(Product(
            store="ouritsumatcha.pl",
            name=name,
            url=href,
            in_stock=not out_of_stock,
            price=price,
        ))
    return products


def scrape_lunetea() -> list[Product]:
    """Shopify store: https://lunetea.pl - use products.json for reliability."""
    base = "https://lunetea.pl"
    products: list[Product] = []

    try:
        data = json.loads(
            fetch(f"{base}/collections/matcha/products.json?limit=250"))
        for p in data.get("products", []):
            name = p.get("title", "")
            handle = p.get("handle", "")
            url = f"{base}/products/{handle}"
            variants = p.get("variants", [])
            in_stock = any(v.get("available") for v in variants)
            price = ""
            if variants:
                price = f"{variants[0].get('price', '')} PLN"
            products.append(Product(
                store="lunetea.pl",
                name=name,
                url=url,
                in_stock=in_stock,
                price=price,
            ))
        return products
    except Exception as e:
        log.warning("lunetea JSON failed (%s); falling back to HTML", e)

    # HTML fallback
    html = fetch(f"{base}/collections/matcha")
    soup = BeautifulSoup(html, "html.parser")
    for card in soup.select("[class*=product-card], li.grid__item, .product-item"):
        a = card.find("a", href=True)
        name_el = card.select_one("[class*=title], h3, h2")
        if not a or not name_el:
            continue
        name = name_el.get_text(strip=True)
        url = urljoin(base, a["href"])
        text = card.get_text(" ", strip=True).lower()
        out = "sold out" in text or "wyprzedane" in text or "niedostępn" in text
        products.append(Product(
            store="lunetea.pl", name=name, url=url, in_stock=not out,
        ))
    return products


def scrape_oromatcha() -> list[Product]:
    """https://oromatcha.com/pl/menu/matcha-164.html"""
    url = "https://oromatcha.com/pl/menu/matcha-164.html"
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    products: list[Product] = []

    # Try common product-card selectors
    cards = soup.select(
        ".product, .product-item, li.item.product, .product-card, "
        "article.product, .products-grid li, .product-thumb"
    )
    if not cards:
        # Generic fallback: any anchor that looks like a product link
        cards = [a.parent for a in soup.select(
            "a[href*='.html']") if a.find("img")]

    seen = set()
    for card in cards:
        a = card.find("a", href=True)
        if not a:
            continue
        href = urljoin(url, a["href"])
        if href in seen or "matcha" not in href.lower():
            continue
        seen.add(href)

        name_el = (card.select_one(".product-name, .name, h2, h3, .product-title")
                   or a)
        name = name_el.get_text(" ", strip=True)
        if not name:
            continue

        price_el = card.select_one(".price, .product-price")
        price = price_el.get_text(" ", strip=True) if price_el else ""

        text = card.get_text(" ", strip=True).lower()
        out = any(s in text for s in (
            "niedostępn", "brak w magazyn", "wyprzedan", "out of stock",
        ))
        # If theres an explicit "add to cart" button/form, treat as in stock.
        if card.select_one("form[action*='cart'], button[name='add']"):
            out = False

        products.append(Product(
            store="oromatcha.com",
            name=name,
            url=href,
            in_stock=not out,
            price=price,
        ))
    return products


SCRAPERS: list[Callable[[], list[Product]]] = [
    scrape_ouritsumatcha,
    scrape_lunetea,
    scrape_oromatcha,
]


def load_state() -> dict[str, bool]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            log.warning("Could not read state file; starting fresh.")
    return {}


def save_state(state: dict[str, bool]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False),
                          encoding="utf-8")


def notify(subject: str, body: str) -> None:
    if NOTIFY_CONSOLE:
        log.info("ALERT: %s\n%s", subject, body)

    if SMTP_HOST and EMAIL_TO:
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = EMAIL_FROM or SMTP_USER
            msg["To"] = EMAIL_TO
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
                s.starttls()
                if SMTP_USER:
                    s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)
            log.info("Email sent to %s", EMAIL_TO)
        except Exception as e:
            log.error("Email failed: %s", e)

    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": f"*{subject}*\n\n{body}",
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False,
                },
                timeout=10,
            )
        except Exception as e:
            log.error("Telegram failed: %s", e)

    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(
                DISCORD_WEBHOOK_URL,
                json={"content": f"**{subject}**\n{body}"},
                timeout=10,
            )
        except Exception as e:
            log.error("Discord failed: %s", e)


def check_once() -> None:
    state = load_state()
    new_state = dict(state)

    for scraper in SCRAPERS:
        try:
            products = scraper()
        except Exception as e:
            log.error("Scraper %s failed: %s", scraper.__name__, e)
            continue

        ceremonial = [p for p in products if is_ceremonial(p.name)]
        log.info("%s: %d products, %d ceremonial",
                 scraper.__name__, len(products), len(ceremonial))

        for p in ceremonial:
            was_in_stock = state.get(p.key(), False)
            if p.in_stock and not was_in_stock:
                notify(
                    subject=f"[BACK IN STOCK] {p.name}",
                    body=(
                        f"Store : {p.store}\n"
                        f"Name  : {p.name}\n"
                        f"Price : {p.price}\n"
                        f"URL   : {p.url}\n"
                    ),
                )
            elif not p.in_stock and was_in_stock:
                log.info("Now OOS: %s (%s)", p.name, p.store)

            new_state[p.key()] = p.in_stock

    save_state(new_state)


def main() -> None:
    log.info("Matcha monitor started. Interval: %ds", CHECK_INTERVAL_SECONDS)
    while True:
        try:
            check_once()
        except KeyboardInterrupt:
            log.info("Stopping.")
            return
        except Exception as e:
            log.exception("Unexpected error: %s", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
