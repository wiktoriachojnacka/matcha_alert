# matcha_alert
Python web scraper that monitors online stores for ceremonial matcha availability and sends alerts when products are back in stock

in progress...

# sites to check
https://ouritsumatcha.pl/kategoria-produktu/herbaty/matcha/
https://lunetea.pl/collections/matcha
https://oromatcha.com/pl/menu/matcha-164.html

## Quick start (Windows)
```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python scraper.py

