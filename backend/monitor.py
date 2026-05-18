import asyncio
import re
from playwright.async_api import async_playwright
from amazon_monitor import AmazonMonitor


class StockMonitor:
    """
    Platform router — delegates to the right scraper based on URL.
    Supported: Flipkart (flipkart.com), Amazon India (amazon.in)
    """

    def __init__(self):
        self._amazon = AmazonMonitor()

    async def check_once(self, url: str, pincode: str | None = None) -> dict:
        if "amazon.in" in url or "amazon.com/dp" in url:
            result = await self._amazon.check_once(url)
            # Amazon doesn't support pincode checks, but echo the pincode back for API consistency
            if pincode:
                result["pincode"] = pincode
            return result
        return await self._check_flipkart(url, pincode=pincode)

    # ═══════════════════════════════════════════════════════════════════
    #  Flipkart scraper
    # ═══════════════════════════════════════════════════════════════════

    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )

    async def _check_flipkart(self, url: str, pincode: str | None = None) -> dict:
        """Check stock for a Flipkart product URL, optionally filtered by pincode."""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
                )
                ctx = await browser.new_context(
                    user_agent=self.USER_AGENT,
                    viewport={"width": 1366, "height": 768},
                    locale="en-IN",
                )
                # Mask webdriver detection
                await ctx.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
                )
                page = await ctx.new_page()

                await page.goto(url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(3)

                title  = await self._get_title(page)
                price  = await self._get_price(page)
                image  = await self._get_image(page)

                # --- Pincode check ---
                pincode_result = None
                if pincode:
                    pincode_result = await self._check_pincode(page, pincode)

                in_stock, stock_label = await self._check_stock(page, pincode_result)

                await browser.close()

                return {
                    "title":          title,
                    "price":          price,
                    "in_stock":       in_stock,
                    "stock_label":    stock_label,
                    "image":          image,
                    "url":            url,
                    "platform":       "flipkart",
                    "pincode":        pincode,
                    "pincode_result": pincode_result,
                    "error":          None,
                }

        except Exception as e:
            return {
                "title":          "Error fetching product",
                "price":          None,
                "in_stock":       False,
                "stock_label":    "Error",
                "image":          None,
                "url":            url,
                "platform":       "flipkart",
                "pincode":        pincode,
                "pincode_result": None,
                "error":          str(e),
            }

    # ────────────────────────────────────────────────────────── helpers ──

    async def _get_title(self, page) -> str:
        try:
            for sel in ["h1 span", "h1", ".B_NuCI", "._35KyD6"]:
                el = await page.query_selector(sel)
                if el:
                    return (await el.inner_text()).strip()
            return "Unknown Product"
        except Exception:
            return "Unknown Product"

    async def _get_price(self, page) -> str | None:
        """Extract price using robust CSS selectors and localized search."""
        try:
            for sel in [
                "div[class*='nx3Z3z']", "span[class*='nx3Z3z']",
                "div[class*='_30jeq3']", "span[class*='_30jeq3']",
                "div[class*='_16Jk6d']",
                "a[class*='_1psv1zeb9']", "a[class*='_1o6mltljo']",
                "._30jeq3._16Jk6d", "._30jeq3", "._16Jk6d",
            ]:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        text = (await el.inner_text()).strip()
                        m = re.search(r'₹[\s]*([\d,]+)', text)
                        if m:
                            return "₹" + m.group(1).replace(" ", "")
                except Exception:
                    continue

            # Localized search: elements near H1 with ₹
            h1 = await page.query_selector("h1")
            if h1:
                parent = await h1.property("parentElement")
                if parent:
                    els = await parent.query_selector_all("*:has-text('₹')")
                    for el in els:
                        text = (await el.inner_text()).strip()
                        if len(text) < 20:
                            m = re.search(r'₹[\s]*([\d,]+)', text)
                            if m:
                                return "₹" + m.group(1).replace(" ", "")

            # Last fallback: global regex
            html = await page.content()
            matches = re.findall(r'₹[\s]*([\d,]+)', html)
            if matches:
                return "₹" + matches[0].replace(" ", "")
            return None
        except Exception:
            return None

    async def _get_image(self, page) -> str | None:
        try:
            for sel in ["._396cs4", "._2r_T1I img", "img.q6DClP", "._2amPTt img", "img[class*='DByuf4']"]:
                el = await page.query_selector(sel)
                if el:
                    src = await el.get_attribute("src")
                    if src and src.startswith("http"):
                        return src
            return None
        except Exception:
            return None

    async def _check_pincode(self, page, pincode: str) -> str | None:
        """Enter delivery pincode and return availability message shown by Flipkart."""
        try:
            trigger = None
            for selector in [
                "a:has-text('Select delivery location')",
                "span:has-text('Select delivery location')",
                "div:has-text('Select delivery location')",
                "a:has-text('Deliver to')",
                "span:has-text('Deliver to')",
                "div:has-text('Deliver to')",
                "button:has-text('Change')",
                "span:has-text('Change')",
                "input[placeholder*='pincode']",
                "input[placeholder*='PIN']",
            ]:
                try:
                    el = await page.query_selector(selector)
                    if el and await el.is_visible():
                        trigger = el
                        break
                except Exception:
                    continue

            if not trigger:
                for sel in ["input[placeholder*='incode']", "input[type='tel']", "input[maxlength='6']"]:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        trigger = el
                        break

            if not trigger:
                return None

            tag_name = await trigger.evaluate("el => el.tagName.toLowerCase()")
            if tag_name == "input":
                pincode_input = trigger
            else:
                await trigger.click()
                await asyncio.sleep(2)
                pincode_input = None
                for selector in [
                    "input[placeholder*='Search by area']",
                    "input[placeholder*='pin code']",
                    "input[placeholder*='pincode']",
                    "input[placeholder*='PIN']",
                    "input[type='tel']",
                    "input[type='text']",
                ]:
                    try:
                        el = await page.query_selector(selector)
                        if el and await el.is_visible():
                            pincode_input = el
                            break
                    except Exception:
                        continue

            if not pincode_input:
                return None

            await pincode_input.click()
            await pincode_input.fill("")
            await pincode_input.type(pincode, delay=100)
            await asyncio.sleep(1)

            suggestions = await page.query_selector_all("div:has-text('" + pincode + "')")
            clicked_suggestion = False
            if suggestions:
                for s in suggestions:
                    if await s.is_visible():
                        s_tag = await s.evaluate("el => el.tagName.toLowerCase()")
                        if s_tag != "input":
                            await s.click()
                            clicked_suggestion = True
                            await asyncio.sleep(2)
                            break

            if not clicked_suggestion:
                await pincode_input.press("Enter")
                await asyncio.sleep(2)

            confirm_btn = await page.query_selector("div:has-text('Confirm'), button:has-text('Confirm'), *:has-text('Confirm')")
            if confirm_btn and await confirm_btn.is_visible():
                await confirm_btn.click()
                await asyncio.sleep(3)

            delivery_element = None
            for sel in [
                "div:has-text('Delivery details')", "div:has-text('Delivery')",
                "div:has-text('Deliver to')", "span:has-text('Deliver to')",
                "[class*='delivery']",
            ]:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        parent = await el.property("parentElement")
                        if parent:
                            delivery_element = parent
                            break
                except Exception:
                    continue

            delivery_text = ""
            if delivery_element:
                delivery_text = (await delivery_element.inner_text()).lower()
            else:
                body_el = await page.query_selector("body")
                if body_el:
                    delivery_text = (await body_el.inner_text()).lower()

            clean_text = delivery_text.replace("exchange", "").replace("card offer", "")

            if any(x in clean_text for x in ("not available", "not deliverable", "not serviceable", "does not deliver")):
                return "Not available at this Pincode"

            m = re.search(r'(delivery by [^<"\n]{5,40}|get it by [^<"\n]{5,40}|delivery in [^<"\n]{5,40})', clean_text)
            if m:
                return m.group(1).title()

            if pincode in clean_text or "jamshedpur" in clean_text:
                return f"Deliverable ({pincode})"

            return "Deliverable to this Pincode"

        except Exception:
            return None

    async def _check_stock(self, page, pincode_result: str | None = None) -> tuple[bool, str]:
        """Determine Flipkart stock status from visible page elements."""
        if pincode_result and "not available" in pincode_result.lower():
            return False, "Not Available in Your Area"

        add_to_cart_el = await page.query_selector("button:has-text('Add to Cart'), div:has-text('Add to Cart'), a:has-text('Add to Cart'), *:has-text('Add to Cart')")
        buy_now_el     = await page.query_selector("button:has-text('Buy Now'), div:has-text('Buy Now'), a:has-text('Buy Now'), *:has-text('Buy Now')")

        has_add_to_cart = bool(add_to_cart_el and await add_to_cart_el.is_visible())
        has_buy_now     = bool(buy_now_el     and await buy_now_el.is_visible())

        notify_me_el = await page.query_selector("button:has-text('Notify Me'), div:has-text('Notify Me'), *:has-text('Notify Me')")
        sold_out_el  = await page.query_selector("button:has-text('Sold Out'), div:has-text('Sold Out'), *:has-text('Sold Out')")
        oos_el       = await page.query_selector("div:has-text('currently out of stock'), div:has-text('out of stock'), *:has-text('currently out of stock')")

        has_notify_me = bool(notify_me_el and await notify_me_el.is_visible())
        has_sold_out  = bool(sold_out_el  and await sold_out_el.is_visible())
        has_oos       = bool(oos_el       and await oos_el.is_visible())

        if has_notify_me or has_sold_out or has_oos:
            if has_sold_out:  return False, "Sold Out"
            if has_notify_me: return False, "Notify Me (Out of Stock)"
            return False, "Out of Stock"

        if has_add_to_cart or has_buy_now:
            return True, "In Stock"

        body_el = await page.query_selector("body")
        lower = (await body_el.inner_text()).lower() if body_el else ""

        if "notify me" in lower or "sold out" in lower or "currently out of stock" in lower:
            return False, "Out of Stock"
        if "add to cart" in lower or "buy now" in lower:
            return True, "In Stock"

        return False, "Status Unknown"
