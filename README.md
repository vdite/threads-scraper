# Threads Recursive Deep Scraper 🧵

Standard Threads scrapers usually fail when it comes to nested replies. They only see the surface. This Python script uses a recursive "Breadth-First Search" approach to find every single comment, even those hidden deep within sub-threads or split posts (1/3, 2/3, etc.).

## Why this exists
Meta's architecture loads replies lazily via GraphQL. If you only scrape the initial HTML, you miss out on the most interesting discussions. This tool automatically identifies comments with further replies, generates their specific URLs, and scrapes them recursively.

## Features
- **Deep Scraping:** Finds nested replies that other tools miss.
- **Recursive Logic:** Automatically follows sub-threads.
- **Human Readable Output:** Prints a clean, numbered list directly to your terminal.
- **Data Safety:** Saves raw results as `last_scrape.json` for further analysis.
- **Network Interception:** Uses Playwright to catch background GraphQL responses.

## Installation

1. Clone this repository or download the script.
2. Install the required dependencies:
   ```bash
   pip install playwright parsel nested-lookup jmespath
   ```
3. Install the Chromium browser for Playwright:
   ```bash
   python3 -m playwright install chromium
   ```

## Usage
Simply run the script and provide a Threads URL as an argument:
```bash   
python3 threads_scraper.py https://www.threads.net/@user/post/CODE
```
