# 🛒 ShopBot — Multi-Platform Stock Tracker

> Real-time stock & price monitoring for **Flipkart** and **Amazon** — with Telegram alerts and a live web dashboard.

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green?style=flat-square&logo=fastapi)
![Playwright](https://img.shields.io/badge/Playwright-1.44-orange?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)

---

## ✨ Features

| Feature | Description |
|---|---|
| **Multi-platform** | Supports Flipkart and Amazon product URLs |
| **Instant Check** | Paste any URL and get stock status in seconds |
| **Price Extraction** | Automatically extracts the current selling price |
| **Watchlist** | Add products to monitor continuously in the background |
| **Real-time Updates** | WebSocket-powered live status — no refresh needed |
| **Check History** | Log of all checks with timestamps and prices |
| **Telegram Alerts** | Get notified the moment a product comes back in stock |
| **Pincode Delivery** | Check Flipkart deliverability for a specific pincode |
| **Modern UI** | Dark luxury-tech design, fully responsive |

---

## 🚀 Quick Start

```bash
git clone https://github.com/satiricalguru/ShopBot.git
cd ShopBot
chmod +x start.sh
./start.sh
```

Then open **http://localhost:8000** in your browser.

---

## Screenshots

<img width="2928" height="1512" alt="image" src="https://github.com/user-attachments/assets/12ef1f32-c175-4f88-b239-97ba2718edb3" />




---

## 📁 Project Structure

```
ShopBot/
├── backend/
│   ├── app.py              # FastAPI server (REST + WebSocket)
│   ├── monitor.py          # Platform router (Flipkart + Amazon)
│   ├── amazon_monitor.py   # Amazon scraper
│   ├── notifier.py         # Telegram notification handler
│   └── requirements.txt
├── frontend/
│   └── index.html          # Single-page web app (no build step)
├── .env.example            # Environment variable template
├── .gitignore
├── start.sh                # One-command launcher
└── README.md
```

---

## ⚙️ Configuration

### Telegram Notifications (optional)

No `.env` editing needed. Open the app at **http://localhost:8000**, click ⚙️ Settings, and paste your credentials there. They are saved permanently to `settings.json` (gitignored) and survive server restarts.

| Field | Where to get it |
|---|---|
| **Bot Token** | Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token |
| **Chat ID** | Message your bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` |

> **Telegram is optional.** The app works without it — you just won't receive push notifications.

The only thing in `.env` is the default check interval:

```env
CHECK_INTERVAL=30
```

---

## 🛠 Manual Setup

If you prefer not to use `start.sh`:

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r backend/requirements.txt
playwright install chromium
cp .env.example .env            # Only needed to customise CHECK_INTERVAL
cd backend
uvicorn app:app --reload --port 8000
```

Then open **http://localhost:8000** and add your Telegram credentials via ⚙️ Settings.

---

## 🔍 How It Works

1. **Playwright** (headless Chromium) navigates to the product page
2. For **Flipkart**: checks for `"Add to Cart"` / `"Buy Now"` buttons (in-stock) and `"Notify Me"` / `"Sold Out"` text (out-of-stock). Optionally checks pincode-level deliverability.
3. For **Amazon**: reads the `#availability` span and checks for `#add-to-cart-button` visibility
4. Results — including price, image, and platform — are returned over HTTP + WebSocket
5. If the product is in stock and Telegram is configured, an alert is sent immediately with the platform name

---

## ⚠️ Notes

- **Amazon anti-bot**: Amazon aggressively blocks headless browsers. Checks may occasionally fail with a CAPTCHA notice — this is expected. Reduce watchlist frequency or use it for one-off checks.
- **Credentials**: Telegram token and chat ID are entered via the Settings UI and saved to `settings.json` (gitignored). They are never stored in `.env` or committed to git.
- **CORS**: `allow_origins=["*"]` is set for local development. Restrict this if you deploy the backend publicly.
- **Data persistence**: watchlist and history are in-memory and reset on server restart. Settings (credentials + interval) persist across restarts via `settings.json`.

---

## 🗺 Roadmap

- [ ] Persistent watchlist (SQLite / JSON)
- [ ] Meesho support
- [ ] Browser extension mode
- [ ] Price history chart

---

## 📝 License

MIT — see [LICENSE](LICENSE)

---

## ✅ Before Publishing

1. **Credentials are safe** — token and chat ID live only in `settings.json`, which is gitignored. They are never in `.env` or any committed file.
2. **Restrict CORS** — change `allow_origins=["*"]` in `backend/app.py` to your actual origin if deploying publicly.
