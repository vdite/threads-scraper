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
cd threads-recursive-scraper

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

Start the scraper by providing any Threads URL as a command-line argument:

```bash
python3 threads_scraper.py https://www.threads.net/@user/post/CODE

```

### Output
The threads scraper gives you a json formatted output 

### Extracted Data Fields:

The scraper captures the following information for every post and reply:

* `author`: Username of the creator.
* `text`: The full content of the post/comment.
* `likes`: Number of likes.
* `reply_count`: Number of sub-replies.
* `code`: The unique identifier used for recursive crawling.


## ⚖️ Disclaimer

This tool is for educational and research purposes only. Please respect Meta's Terms of Service and the robots.txt of threads.net. Use this scraper responsibly and do not overwhelm their servers. They also 'll block your IP, if used roge.
