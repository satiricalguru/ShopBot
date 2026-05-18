import httpx
from datetime import datetime

PLATFORM_LABELS = {
    "flipkart": "🔶 Flipkart",
    "amazon":   "🛒 Amazon",
}

class Notifier:
    """Telegram notification handler."""

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"

    async def send_message(self, text: str):
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(url, json=payload)
                r.raise_for_status()
        except Exception as e:
            print(f"[Notifier] Failed to send message: {e}")

    async def notify_stock(self, title: str, url: str, platform: str = ""):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        platform_label = PLATFORM_LABELS.get(platform, "🛍️ Store")
        msg = (
            f"🚨 <b>IN STOCK ALERT!</b>\n\n"
            f"<b>Platform:</b> {platform_label}\n"
            f"<b>Product:</b> {title}\n"
            f"<b>URL:</b> {url}\n"
            f"<b>Time:</b> {now}"
        )
        await self.send_message(msg)
