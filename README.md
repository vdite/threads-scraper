# 🧵 Threads Scraper - Recursive, nested & deep

**The most powerful Python-based Threads Scraper for extracting full discussions, including nested replies and sub-threads.** A powerful Playwright-based Python tool for full discussion extraction.

Standard scrapers for threads.net often fail to capture the full picture. They only scrape top-level posts and miss the deep conversations happening in the replies. This tool uses a **recursive Breadth-First Search (BFS)** approach to ensure no comment is left behind.


## 🚀 Why this is the best Threads Scraper

While other tools only see the surface, this scraper dives deep into the discussion tree. It is the perfect **Threads API alternative** for researchers, journalists, and creators.

### Key Advantages:

| Feature | Standard Scrapers | **Technickr Deep Scraper** |
| --- | --- | --- |
| Top-level posts | ✅ | ✅ |
| **Nested Replies** | ❌ | ✅ |
| **Sub-thread crawling (1/3, 2/3)** | ❌ | ✅ |
| Lazy-loading handling | Limited | Full (via Playwright) |
| Deduplication | ❌ | ✅ (via Unique ID) |

## ✨ Features

* **Recursive Deep Scraping:** Automatically follows reply chains to extract the entire conversation.
* **Playwright Integration:** Uses headless browser automation to handle Meta's dynamic GraphQL loading.
* **Human-Readable Terminal Output:** Instant feedback with a clean, numbered list of comments.
* **Data Export:** Saves every scrape as a structured `last_scrape.json` for easy post-processing.
* **Smart Deduplication:** Identifies posts by their unique ID to prevent duplicate entries in your dataset.

## 🛠 Installation

1. **Clone the repository:**
```bash
git clone https://github.com/vdite/threads-scraper.git
cd threads-scraper
```

2. **Install dependencies:**
```bash
pip install playwright parsel nested-lookup jmespath
```

3. **Setup Playwright:**
```bash
python3 -m playwright install chromium
```


## 📖 Usage

There are two versions of the scraper. Choose the one that fits your needs:

### Version 1: Basic (no login required)

Start the scraper by providing any Threads URL as a command-line argument:

```bash
python3 threads_scraper.py https://www.threads.net/@user/post/CODE
```

Output is printed as JSON to stdout.

> **Note:** Without login, Threads limits the visible comments to roughly 20 top-level threads (~45-50 posts total including sub-replies). The page literally says *"Log in to see more replies."* at the bottom.

---

### Version 2: Enhanced with Login (`threads_scraper_v2.py`)

This version adds **cookie-based authentication**, a **live progress bar**, **automatic output files**, and **aggressive scroll + button handling** to capture significantly more comments.

#### Why use the login version?

| | Basic (v1) | **Enhanced (v5)** |
| --- | --- | --- |
| Comments captured | ~45-50 | **~76+** (up to 60% more) |
| Login support | ❌ | ✅ (cookie-based) |
| Live progress bar | ❌ | ✅ |
| Auto output file | ❌ | ✅ (`out-DD.HH.MM.json`) |
| Scroll strategy | 3x fixed | Dynamic (until exhausted) |
| "Load more" buttons | ❌ | ✅ (auto-click, EN + DE) |
| Max pages | 15 | 100 (configurable) |
| Ajax response parsing | ❌ | ✅ (`for (;;);` handling) |

#### Step 1: Login (one-time)

```bash
python3 threads_scraper_v2.py --login
```

A browser window opens. Log in to your Threads/Instagram account. Once the `sessionid` cookie is detected, the browser closes and all cookies are saved to `threads_cookies.json`.

#### Step 2: Scrape

```bash
# Default (max 100 pages)
python3 threads_scraper_v2.py "https://www.threads.com/@user/post/CODE"

# With custom page limit
python3 threads_scraper_v2.py "https://www.threads.com/@user/post/CODE" 200
```

The terminal shows a live progress bar:

```
  [████████████░░░░░░░░░░░░░░░░░░] 12/100  | Found: 87  | Queue: 23  | Time: 01:34  | threads.net/@user/post/ABC  scrolling...
```

Results are saved automatically to a timestamped file like `out-25.14.30.json`.

#### Managing your session

```bash
# Delete saved cookies
python3 threads_scraper_v2.py --logout

# Show help
python3 threads_scraper_v2.py --help
```

> **Tip:** The scraper also works without login — it simply falls back to the limited logged-out view (~50 comments).


## ⚖️ Disclaimer

This tool is for educational and research purposes only. Please respect Meta's Terms of Service and the robots.txt of threads.net. Use this scraper responsibly and do not overwhelm their servers. They also 'll block your IP, if used rogue.
