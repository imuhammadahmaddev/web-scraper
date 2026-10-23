# Multi-Platform Web Scraper

A lightweight, API-free multi-platform web scraper built with Python, Streamlit, Selenium, and BeautifulSoup.

## Features

- **Multi-Platform Support**: Scrape public results across Blogs, Facebook, X (Twitter), YouTube, Instagram, and TikTok.
- **Date Filter**: Filter results from 1 to 365 past days.
- **No APIs Required**: Uses headless browser automation and search index operators to collect public snippets and URLs without requiring API credentials or login walls.
- **Data Export**: Export scraped results directly to CSV format.
- **Interactive UI**: Clean and intuitive Streamlit dashboard.

## Requirements

- Python 3.10+
- Google Chrome browser (for Selenium ChromeDriver)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/imuhammadahmaddev/web-scraper.git
   cd web-scraper
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Start the Streamlit web application:

```bash
streamlit run app.py
```
*(Or `python -m streamlit run app.py`)*

1. Enter your search keyword in the input box.
2. Select the past days filter (1–365 days).
3. Select the target platforms.
4. Click **Start Scraping**.
5. Download your extracted data using the **Download Results as CSV** button.
