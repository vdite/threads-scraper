import json
import asyncio
import sys
from typing import Dict, List, Optional
from urllib.parse import urlsplit
from playwright.async_api import async_playwright
from parsel import Selector
from nested_lookup import nested_lookup

def normalize_url(url: str) -> str:
    """Canonical post URL: threads.com host, no query string, fragment or trailing slash."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if host in ("threads.net", "www.threads.net", "threads.com", "www.threads.com"):
        host = "www.threads.com"
    return f"https://{host}{parts.path.rstrip('/')}"


def collect_posts(data, extracted_comments: Dict, urls_to_visit: List[str], visited_urls: set):
    """Stores every post found in a JSON payload and queues posts that have replies."""
    for post_obj in nested_lookup("post", data):
        parsed = parse_post(post_obj)
        if parsed and parsed.get("id"):
            extracted_comments[parsed["id"]] = parsed
            if parsed.get("reply_count", 0) > 0 and parsed.get("code"):
                new_url = f"https://www.threads.com/@{parsed['author']}/post/{parsed['code']}"
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
            "reply_count": (post_data.get("text_post_app_info") or {}).get("direct_reply_count") or 0
        }
    except Exception:
        return None

async def scrape_threads_recursive(start_url: str, max_pages: int = 15) -> List[Dict]:
    start_url = normalize_url(start_url)
    extracted_comments = {}
    urls_to_visit = [start_url]
    visited_urls = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(locale="en-US")
        page = await context.new_page()

        # Define listener once outside the loop
        async def handle_response(response):
            if "graphql" in response.url:
                try:
                    collect_posts(await response.json(), extracted_comments, urls_to_visit, visited_urls)
                except Exception:
                    pass

        # Bind listener only once to the page
        page.on("response", handle_response)

        while urls_to_visit and len(visited_urls) < max_pages:
            current_url = urls_to_visit.pop(0)

            if current_url in visited_urls:
                continue

            visited_urls.add(current_url)

            try:
                await page.goto(current_url, wait_until="networkidle")

                for _ in range(3):
                    await page.mouse.wheel(0, 1000)
                    await page.wait_for_timeout(800)

                html = await page.content()

                selector = Selector(text=html)
                for script in selector.xpath('//script/text()').getall():
                    try:
                        start_index = script.find('{')
                        end_index = script.rfind('}') + 1
                        if start_index == -1 or end_index == 0:
                            continue

                        data = json.loads(script[start_index:end_index])
                        collect_posts(data, extracted_comments, urls_to_visit, visited_urls)
                    except (json.JSONDecodeError, AttributeError):
                        continue

            except Exception:
                pass

        await browser.close()

    print(f"---> Pages visited (incl. sub-comments): {len(visited_urls)}", file=sys.stderr)
    return list(extracted_comments.values())

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 threads_scraper.py <threads_url> > out.json", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]

    results = asyncio.run(scrape_threads_recursive(url, max_pages=15))

    if results:
        # Only JSON goes to stdout, so `> out.json` produces a valid file.
        print(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"---> Total posts/comments found: {len(results)}", file=sys.stderr)
    else:
        print("No data could be extracted.", file=sys.stderr)
