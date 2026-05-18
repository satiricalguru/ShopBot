import asyncio
import re
from playwright.async_api import async_playwright


class AmazonMonitor:
    """Playwright-based Amazon stock, price, and availability checker."""

    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )

    async def check_once(self, url: str, **_kwargs) -> dict:
        """Check stock for an Amazon.in product URL."""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-web-security",
                    ],
                )
                ctx = await browser.new_context(
                    user_agent=self.USER_AGENT,
                    viewport={"width": 1366, "height": 768},
                    locale="en-IN",
                    extra_http_headers={
                        "Accept-Language": "en-IN,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                )
                await ctx.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
                )
                page = await ctx.new_page()

                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(3)

                # Handle CAPTCHA / robot check page
                page_text = await page.inner_text("body")
                if "robot" in page_text.lower() or "captcha" in page_text.lower():
                    await browser.close()
                    return self._error_result(url, "Amazon blocked the request (CAPTCHA). Try again later.")

                title  = await self._get_title(page)
                price  = await self._get_price(page)
                image  = await self._get_image(page)
                in_stock, stock_label = await self._check_stock(page)

                await browser.close()
                return {
                    "title":          title,
                    "price":          price,
                    "in_stock":       in_stock,
                    "stock_label":    stock_label,
                    "image":          image,
                    "url":            url,
                    "platform":       "amazon",
                    "pincode":        None,
                    "pincode_result": None,
                    "error":          None,
                }

        except Exception as e:
            return self._error_result(url, str(e))

    # ────────────────────────────────────────────────────────── helpers ──

    def _error_result(self, url: str, msg: str) -> dict:
        return {
            "title":          "Error fetching product",
            "price":          None,
            "in_stock":       False,
            "stock_label":    "Error",
            "image":          None,
            "url":            url,
            "platform":       "amazon",
            "pincode":        None,
            "pincode_result": None,
            "error":          msg,
        }

    async def _get_title(self, page) -> str:
        try:
            for sel in ["#productTitle", "h1.product-title-word-break", "h1"]:
                el = await page.query_selector(sel)
                if el:
                    return (await el.inner_text()).strip()
            return "Unknown Product"
        except Exception:
            return "Unknown Product"

    async def _get_price(self, page) -> str | None:
        try:
            # Amazon price selectors (INR)
            for sel in [
                "#priceblock_ourprice",
                "#priceblock_dealprice",
                "#priceblock_saleprice",
                ".a-price .a-offscreen",
                "#corePrice_feature_div .a-price .a-offscreen",
                "#apex_offerDisplay_desktop .a-price .a-offscreen",
                "#tp_price_block_total_price_ww .a-price .a-offscreen",
                ".priceToPay .a-price .a-offscreen",
                ".priceToPay span[aria-hidden]",
                "#price_inside_buybox",
            ]:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        text = (await el.inner_text()).strip()
                        if text:
                            # Normalise ₹ symbol (Amazon uses both ₹ and unicode variants)
                            text = text.replace("\u20b9", "₹").replace("\xa0", "")
                            m = re.search(r'[₹\u20b9][\s]*([\d,]+)', text)
                            if m:
                                return "₹" + m.group(1).replace(" ", "")
                except Exception:
                    continue

            # Fallback: scan HTML
            html = await page.content()
            matches = re.findall(r'[₹\u20b9]\s*([\d,]{3,})', html)
            if matches:
                return "₹" + matches[0]
            return None
        except Exception:
            return None

    async def _get_image(self, page) -> str | None:
        try:
            for sel in ["#landingImage", "#imgBlkFront", "#main-image", "#imageBlock img"]:
                el = await page.query_selector(sel)
                if el:
                    src = await el.get_attribute("src")
                    if src and src.startswith("http"):
                        return src
                    # Amazon sometimes uses data-old-hires for hi-res
                    src = await el.get_attribute("data-old-hires")
                    if src and src.startswith("http"):
                        return src
            return None
        except Exception:
            return None

    async def _check_stock(self, page) -> tuple[bool, str]:
        try:
            # 1. Explicit availability span
            avail_el = await page.query_selector("#availability span")
            if avail_el:
                avail_text = (await avail_el.inner_text()).strip().lower()
                if any(x in avail_text for x in ("in stock", "usually ships", "ships soon", "available")):
                    return True, "In Stock"
                if any(x in avail_text for x in ("currently unavailable", "out of stock", "not available")):
                    return False, "Out of Stock"

            # 2. Add to Cart / Buy Now buttons
            atc = await page.query_selector("#add-to-cart-button")
            bn  = await page.query_selector("#buy-now-button")
            has_atc = atc and await atc.is_visible() if atc else False
            has_bn  = bn  and await bn.is_visible()  if bn  else False

            if has_atc or has_bn:
                return True, "In Stock"

            # 3. "Currently unavailable" block
            unavail = await page.query_selector("#outOfStock, #availability-brief")
            if unavail and await unavail.is_visible():
                return False, "Out of Stock"

            # 4. Full-page text fallback
            body = await page.query_selector("body")
            lower = (await body.inner_text()).lower() if body else ""
            if "currently unavailable" in lower or "out of stock" in lower:
                return False, "Out of Stock"
            if "add to cart" in lower or "buy now" in lower:
                return True, "In Stock"

            return False, "Status Unknown"
        except Exception:
            return False, "Status Unknown"
