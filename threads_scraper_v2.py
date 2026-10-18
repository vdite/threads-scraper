import json
import asyncio
import sys
import os
import time
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlsplit
from playwright.async_api import async_playwright
from parsel import Selector
from nested_lookup import nested_lookup

COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "threads_cookies.json")

USAGE = """Usage: python3 threads_scraper_v2.py <threads_url> [max_pages]
       python3 threads_scraper_v2.py --login        (log in and save cookies)
       python3 threads_scraper_v2.py --logout       (delete saved cookies)
       python3 threads_scraper_v2.py --help         (show this help)"""


def normalize_url(url: str) -> str:
    """Canonical post URL: threads.com host, no query string, fragment or trailing slash.

    Threads moved from threads.net to threads.com and share links carry tracking
    parameters, so the same post can appear under several URLs.
    """
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if host in ("threads.net", "www.threads.net", "threads.com", "www.threads.com"):
        host = "www.threads.com"
    return f"https://{host}{parts.path.rstrip('/')}"


def post_url(parsed: Dict) -> str:
    return f"https://www.threads.com/@{parsed['author']}/post/{parsed['code']}"


def collect_posts(data, extracted_comments: Dict, urls_to_visit: List[str], visited_urls: set):
    """Stores every post found in a JSON payload and queues posts that have replies."""
    for post_obj in nested_lookup("post", data):
        parsed = parse_post(post_obj)
        if parsed and parsed.get("id"):
            extracted_comments[parsed["id"]] = parsed
            if parsed.get("reply_count", 0) > 0 and parsed.get("code"):
                new_url = post_url(parsed)
                if new_url not in visited_urls and new_url not in urls_to_visit:
                    urls_to_visit.append(new_url)


def parse_post(post_data: Dict) -> Optional[Dict]:
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
            "reply_count": (post_data.get("text_post_app_info") or {}).get("direct_reply_count") or 0,
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


async def scroll_and_expand(page, extracted_comments: Dict, max_stale_rounds: int = 12, max_rounds: int = 60):
    """Scrolls and clicks load-more buttons until no new content appears.

    A click alone does not count as progress: a button that stays visible would
    otherwise keep the loop alive forever. max_rounds is a hard upper bound.
    """

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
    rounds = 0

    while stale_rounds < max_stale_rounds and rounds < max_rounds:
        rounds += 1
        # Scroll down
        await page.mouse.wheel(0, 4000)
        await page.wait_for_timeout(1500)

        # Click any "load more" / "show replies" buttons
        for sel in load_more_selectors:
            try:
                buttons = await page.locator(sel).all()
                for button in buttons:
                    try:
                        if await button.is_visible():
                            await button.click(timeout=2000)
                            await page.wait_for_timeout(2000)
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
    # The session cookie grants full account access: keep the file private to this user.
    fd = os.open(COOKIE_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(cookies, f, indent=2)
    os.chmod(COOKIE_FILE, 0o600)

    auth_cookies = [c["name"] for c in cookies if c["name"] in ("sessionid", "ds_user_id", "ig_did", "mid")]
    print(f"\n  Cookies saved to: {COOKIE_FILE}", file=sys.stderr)
    print(f"  {len(cookies)} cookies stored (auth: {', '.join(auth_cookies) if auth_cookies else 'NONE'})\n", file=sys.stderr)

    await browser.close()
    return cookies


async def scrape_threads_recursive(start_url: str, max_pages: int = 100) -> List[Dict]:
    start_url = normalize_url(start_url)
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
                    collect_posts(await response.json(), extracted_comments, urls_to_visit, visited_urls)
                except Exception:
                    pass

            # Also try parsing "for (;;);" prefixed JSON from ajax endpoints
            if "/ajax/" in url:
                try:
                    text = await response.text()
                    if text.startswith("for (;;);"):
                        text = text[len("for (;;);"):]
                    collect_posts(json.loads(text), extracted_comments, urls_to_visit, visited_urls)
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
                        collect_posts(data, extracted_comments, urls_to_visit, visited_urls)
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


def write_results(results: List[Dict]):
    if not results:
        print("No data could be extracted.", file=sys.stderr)
        return
    # Full date and seconds: runs on different days/months or within one minute must not overwrite each other.
    filename = f"out-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Output written to: {filename}", file=sys.stderr)
    print(f"  Total posts/comments: {len(results)}\n", file=sys.stderr)


async def login():
    async with async_playwright() as pw:
        await do_login(pw)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("--help", "-h"):
        print(USAGE)
        sys.exit(0 if args else 1)

    if args[0] == "--login":
        asyncio.run(login())
        return

    if args[0] == "--logout":
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
            print("Cookies deleted.")
        else:
            print("No cookies found.")
        return

    if args[0].startswith("-"):
        print(f"Unknown option: {args[0]}\n\n{USAGE}", file=sys.stderr)
        sys.exit(1)

    max_pages = 100
    if len(args) > 1:
        try:
            max_pages = int(args[1])
        except ValueError:
            max_pages = 0
        if max_pages < 1:
            print(f"max_pages must be a positive number, got: {args[1]}", file=sys.stderr)
            sys.exit(1)

    write_results(asyncio.run(scrape_threads_recursive(args[0], max_pages=max_pages)))


if __name__ == "__main__":
    main()
