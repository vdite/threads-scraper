import json
import asyncio
import sys
import os
import time
from datetime import datetime
from typing import Dict, List
from playwright.async_api import async_playwright
from parsel import Selector
from nested_lookup import nested_lookup

COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "threads_cookies.json")


def parse_post(post_data: Dict) -> Dict:
    """Extracts the data including the 'code' for URL generation."""
    if not isinstance(post_data, dict):
        return None

    try:
        caption = post_data.get("caption") or {}
        text = caption.get("text")

        user = post_data.get("user") or {}
        author = user.get("username")

        if not text or not author:
            return None

        return {
            "id": post_data.get("id"),
            "code": post_data.get("code"),
            "text": text,
            "author": author,
            "likes": post_data.get("like_count", 0),
            "reply_count": post_data.get("text_post_app_info", {}).get("direct_reply_count", 0),
        }
    except Exception:
        return None


def print_progress(page_num: int, max_pages: int, queue_size: int, found: int, current_url: str, start_time: float, phase: str = ""):
    """Prints a live progress bar and stats."""
    elapsed = time.time() - start_time
    minutes, seconds = divmod(int(elapsed), 60)

    bar_width = 30
    ratio = page_num / max_pages if max_pages > 0 else 0
    filled = int(bar_width * ratio)
    bar = "█" * filled + "░" * (bar_width - filled)

    short_url = current_url
    if len(short_url) > 50:
        short_url = short_url[:24] + "..." + short_url[-23:]

    phase_str = f"  {phase}" if phase else ""

    line = (
        f"\r  [{bar}] {page_num}/{max_pages}  "
        f"| Found: {found}  "
        f"| Queue: {queue_size}  "
        f"| Time: {minutes:02d}:{seconds:02d}  "
        f"| {short_url}{phase_str}"
    )

    sys.stderr.write(f"{line:<160}")
    sys.stderr.flush()


async def get_scroll_height(page) -> int:
    return await page.evaluate("document.body.scrollHeight")


async def scroll_and_expand(page, extracted_comments: Dict, max_stale_rounds: int = 12):
    """Scrolls and clicks load-more buttons until no new content appears."""

    load_more_selectors = [
        "text=/View more repli/i",
        "text=/Show hidden repli/i",
        "text=/View all repli/i",
        "text=/more repli/i",
        "text=/Load more/i",
        "text=/See more/i",
        "text=/Show replies/i",
        "text=/View replies/i",
        "text=/Weitere Antworten/i",
        "text=/Mehr anzeigen/i",
        "text=/Antworten anzeigen/i",
    ]

    previous_count = len(extracted_comments)
    previous_scroll_height = await get_scroll_height(page)
    stale_rounds = 0

    while stale_rounds < max_stale_rounds:
        # Scroll down
        await page.mouse.wheel(0, 4000)
        await page.wait_for_timeout(1500)

        # Click any "load more" / "show replies" buttons
        for sel in load_more_selectors:
            try:
                buttons = await page.locator(sel).all()
                for button in buttons:
                    try:
                        if await button.is_visible(timeout=500):
                            await button.click(timeout=2000)
                            await page.wait_for_timeout(2000)
                            stale_rounds = 0  # reset on successful click
                    except Exception:
                        pass
            except Exception:
                pass

        current_count = len(extracted_comments)
        current_scroll_height = await get_scroll_height(page)

        if current_count > previous_count or current_scroll_height > previous_scroll_height:
            previous_count = current_count
            previous_scroll_height = current_scroll_height
            stale_rounds = 0
        else:
            stale_rounds += 1


async def do_login(pw):
    """Opens a visible browser for manual login. Saves cookies afterwards."""
    print("\n  === LOGIN MODE ===", file=sys.stderr)
    print("  A browser window will open. Please log in to Threads/Instagram.", file=sys.stderr)
    print("  After login is complete, cookies will be saved automatically.\n", file=sys.stderr)

    browser = await pw.chromium.launch(headless=False)
    context = await browser.new_context(locale="en-US")
    page = await context.new_page()

    await page.goto("https://www.threads.com/login", wait_until="networkidle", timeout=60000)

    print("  Waiting for login... (complete login in the browser window)", file=sys.stderr)
    print("  Looking for session cookie (sessionid)...\n", file=sys.stderr)

    # Poll for sessionid cookie — the definitive sign of successful login
    logged_in = False
    for attempt in range(300):  # up to 5 minutes (300 x 1s)
        cookies = await context.cookies()
        cookie_names = [c["name"] for c in cookies]

        if "sessionid" in cookie_names:
            logged_in = True
            print("\n  Login detected! (sessionid cookie found)", file=sys.stderr)
            # Wait a bit for all cookies to settle
            await page.wait_for_timeout(3000)
            cookies = await context.cookies()
            break

        await page.wait_for_timeout(1000)

        if attempt % 10 == 0 and attempt > 0:
            print(f"  Still waiting... ({attempt}s elapsed)", file=sys.stderr)

    if not logged_in:
        print("\n  Timeout waiting for login. Saving whatever cookies exist...", file=sys.stderr)

    # Save all cookies (for both .threads.com and .instagram.com)
    with open(COOKIE_FILE, "w") as f:
        json.dump(cookies, f, indent=2)

    auth_cookies = [c["name"] for c in cookies if c["name"] in ("sessionid", "ds_user_id", "ig_did", "mid")]
    print(f"\n  Cookies saved to: {COOKIE_FILE}", file=sys.stderr)
    print(f"  {len(cookies)} cookies stored (auth: {', '.join(auth_cookies) if auth_cookies else 'NONE'})\n", file=sys.stderr)

    await browser.close()
    return cookies


async def scrape_threads_recursive(start_url: str, max_pages: int = 100) -> List[Dict]:
    extracted_comments = {}
    urls_to_visit = [start_url]
    visited_urls = set()
    start_time = time.time()

    has_cookies = os.path.exists(COOKIE_FILE)

    print(f"\n  Starting scrape: {start_url}", file=sys.stderr)
    print(f"  Max pages: {max_pages}", file=sys.stderr)
    print(f"  Cookies: {'loaded' if has_cookies else 'none (run with --login to authenticate)'}\n", file=sys.stderr)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(locale="en-US")

        # Load saved cookies if available
        if has_cookies:
            with open(COOKIE_FILE, "r") as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)

        page = await context.new_page()

        async def handle_response(response):
            url = response.url
            if any(k in url for k in ["graphql", "api/v1"]):
                try:
                    json_data = await response.json()
                    all_posts = nested_lookup("post", json_data)
                    for post_obj in all_posts:
                        parsed = parse_post(post_obj)
                        if parsed and parsed.get("id"):
                            extracted_comments[parsed["id"]] = parsed
                            if parsed.get("reply_count", 0) > 0 and parsed.get("code"):
                                new_url = f"https://www.threads.net/@{parsed['author']}/post/{parsed['code']}"
                                if new_url not in visited_urls and new_url not in urls_to_visit:
                                    urls_to_visit.append(new_url)
                except Exception:
                    pass

            # Also try parsing "for (;;);" prefixed JSON from ajax endpoints
            if "/ajax/" in url:
                try:
                    text = await response.text()
                    if text.startswith("for (;;);"):
                        text = text[len("for (;;);"):]
                    data = json.loads(text)
                    all_posts = nested_lookup("post", data)
                    for post_obj in all_posts:
                        parsed = parse_post(post_obj)
                        if parsed and parsed.get("id"):
                            extracted_comments[parsed["id"]] = parsed
                            if parsed.get("reply_count", 0) > 0 and parsed.get("code"):
                                new_url = f"https://www.threads.net/@{parsed['author']}/post/{parsed['code']}"
                                if new_url not in visited_urls and new_url not in urls_to_visit:
                                    urls_to_visit.append(new_url)
                except Exception:
                    pass

        page.on("response", handle_response)

        page_num = 0
        while urls_to_visit and len(visited_urls) < max_pages:
            current_url = urls_to_visit.pop(0)

            if current_url in visited_urls:
                continue

            visited_urls.add(current_url)
            page_num += 1

            print_progress(page_num, max_pages, len(urls_to_visit), len(extracted_comments), current_url, start_time, "loading...")

            try:
                await page.goto(current_url, wait_until="networkidle", timeout=30000)

                # Extract from embedded JSON in HTML
                print_progress(page_num, max_pages, len(urls_to_visit), len(extracted_comments), current_url, start_time, "parsing...")
                html = await page.content()
                selector = Selector(text=html)
                for script in selector.xpath("//script/text()").getall():
                    try:
                        start_index = script.find("{")
                        end_index = script.rfind("}") + 1
                        if start_index == -1 or end_index == 0:
                            continue

                        data = json.loads(script[start_index:end_index])
                        all_posts = nested_lookup("post", data)

                        for post_obj in all_posts:
                            parsed = parse_post(post_obj)
                            if parsed and parsed.get("id"):
                                extracted_comments[parsed["id"]] = parsed
                                if parsed.get("reply_count", 0) > 0 and parsed.get("code"):
                                    new_url = f"https://www.threads.net/@{parsed['author']}/post/{parsed['code']}"
                                    if new_url not in visited_urls and new_url not in urls_to_visit:
                                        urls_to_visit.append(new_url)
                    except (json.JSONDecodeError, AttributeError):
                        continue

                # Scroll and expand all lazy-loaded content
                print_progress(page_num, max_pages, len(urls_to_visit), len(extracted_comments), current_url, start_time, "scrolling...")
                await scroll_and_expand(page, extracted_comments)

                print_progress(page_num, max_pages, len(urls_to_visit), len(extracted_comments), current_url, start_time, "done")

            except Exception as e:
                sys.stderr.write(f"\n  Error on {current_url}: {e}\n")

        await browser.close()

    sys.stderr.write("\n\n")
    elapsed = time.time() - start_time
    minutes, seconds = divmod(int(elapsed), 60)
    print(f"  Done! Pages visited: {page_num} | Comments found: {len(extracted_comments)} | Time: {minutes:02d}:{seconds:02d}", file=sys.stderr)

    return list(extracted_comments.values())


async def main():
    if len(sys.argv) < 2 or sys.argv[1] == "--help":
        print("Usage: python threads_scraper5.py <threads_url> [max_pages]")
        print("       python threads_scraper5.py --login        (log in and save cookies)")
        print("       python threads_scraper5.py --logout       (delete saved cookies)")
        sys.exit(1)

    if sys.argv[1] == "--login":
        async with async_playwright() as pw:
            await do_login(pw)
        return

    if sys.argv[1] == "--logout":
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
            print("Cookies deleted.")
        else:
            print("No cookies found.")
        return

    url = sys.argv[1]
    max_pg = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    results = asyncio.run(scrape_threads_recursive(url, max_pages=max_pg))

    if results:
        now = datetime.now()
        filename = f"out-{now.strftime('%d.%H.%M')}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"\n  Output written to: {filename}", file=sys.stderr)
        print(f"  Total posts/comments: {len(results)}\n", file=sys.stderr)
    else:
        print("No data could be extracted.", file=sys.stderr)


if __name__ == "__main__":
    # --login uses its own async context, everything else goes through main()
    if len(sys.argv) > 1 and sys.argv[1] == "--login":
        asyncio.run(main())
    elif len(sys.argv) > 1 and sys.argv[1] == "--logout":
        asyncio.run(main())
    else:
        main_url = sys.argv[1] if len(sys.argv) > 1 else None
        max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 100

        if not main_url:
            print("Usage: python threads_scraper5.py <threads_url> [max_pages]")
            print("       python threads_scraper5.py --login")
            print("       python threads_scraper5.py --logout")
            sys.exit(1)

        results = asyncio.run(scrape_threads_recursive(main_url, max_pages=max_pages))

        if results:
            now = datetime.now()
            filename = f"out-{now.strftime('%d.%H.%M')}.json"

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)

            print(f"\n  Output written to: {filename}", file=sys.stderr)
            print(f"  Total posts/comments: {len(results)}\n", file=sys.stderr)
        else:
            print("No data could be extracted.", file=sys.stderr)
