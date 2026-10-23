import streamlit as st
import pandas as pd
import time
import urllib.parse
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import dateparser

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# configuration
def get_driver():
    options = Options()
    options.add_argument("--headless=new")  # background, remove to see browser
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=options)
    return driver


# filter
def is_within_days(date_str, max_days):
    """Checks if a scraped date string ('3 days ago', 'Oct 10, 2026') falls within max_days."""
    if not date_str:
        return True 
    parsed_date = dateparser.parse(date_str)
    if not parsed_date:
        return True
    parsed_date = parsed_date.replace(tzinfo=None)
    cutoff_date = datetime.now() - timedelta(days=max_days)
    return parsed_date >= cutoff_date


#core engine
def scrape_platform(driver, keyword, platform, days):
    results = []
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    platform_queries = {
        "Blogs": f'"{keyword}" -site:facebook.com -site:x.com -site:youtube.com -site:instagram.com -site:tiktok.com after:{cutoff_date}',
        "Facebook": f'site:facebook.com "{keyword}" after:{cutoff_date}',
        "X (Twitter)": f'(site:x.com OR site:twitter.com) "{keyword}" after:{cutoff_date}',
        "Instagram": f'site:instagram.com "{keyword}" after:{cutoff_date}',
        "TikTok": f'site:tiktok.com "{keyword}" after:{cutoff_date}',
    }

    # first Case: direct YT scrapping
    if platform == "YouTube":
        encoded_kw = urllib.parse.quote(keyword)
        # sp=CAISAhAB sorts YouTube results by upload date (AI Helped)
        url = f"https://www.youtube.com/results?search_query={encoded_kw}&sp=CAISAhAB"
        driver.get(url)
        time.sleep(3)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        videos = soup.find_all("ytd-video-renderer", limit=10)

        for v in videos:
            title_el = v.find("a", id="video-title")
            meta_els = v.find_all("span", class_="inline-metadata-item")
            date_text = meta_els[1].text.strip() if len(meta_els) > 1 else ""

            if title_el and is_within_days(date_text, days):
                results.append({
                    "Platform": "YouTube",
                    "Title / Snippet": title_el.text.strip(),
                    "Date": date_text or f"Last {days} days",
                    "URL": "https://www.youtube.com" + title_el["href"]
                })
        return results

    # second Case: Socials & Blogs via Search Index Scraping
    # Uses DuckDuckGo HTML / Google index to bypass Facebook/IG/X login walls
    query = platform_queries[platform]
    encoded_query = urllib.parse.quote(query)
    search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

    driver.get(search_url)
    time.sleep(2)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    items = soup.find_all("div", class_="result__body", limit=10)

    for item in items:
        title_tag = item.find("a", class_="result__a")
        snippet_tag = item.find("a", class_="result__snippet")

        if title_tag:
            title = title_tag.text.strip()
            link = title_tag.get("href", "")
            snippet = snippet_tag.text.strip() if snippet_tag else ""

            results.append({
                "Platform": platform,
                "Title / Snippet": f"{title} — {snippet}",
                "Date": f"Since {cutoff_date} (<= {days} days)",
                "URL": link
            })

    return results


# Streamlite UI
st.set_page_config(page_title="Multi-Platform Web Scraper", layout="wide")
st.title("Multi-Platform Keyword Scraper")

col1, col2 = st.columns([3, 1])

with col1:
    keyword = st.text_input("Enter Keyword to Scrape:", placeholder="e.g., Artificial Intelligence")

with col2:
    # dropdown
    days_option = st.selectbox(
        "Filter by Past Days (1 - 365):",
        options=list(range(1, 366)),
        index=6
    )

platforms_to_scrape = st.multiselect(
    "Select Platforms:",
    ["Blogs", "Facebook", "X (Twitter)", "YouTube", "Instagram", "TikTok"],
    default=["Blogs", "Facebook", "X (Twitter)", "YouTube", "Instagram", "TikTok"]
)

if st.button("Start Scraping", type="primary"):
    if not keyword.strip():
        st.warning("Please enter a keyword first.")
    else:
        all_data = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        driver = get_driver()
        try:
            for idx, platform in enumerate(platforms_to_scrape):
                status_text.text(f"Scraping {platform} for '{keyword}' (Past {days_option} days)...")
                platform_results = scrape_platform(driver, keyword, platform, days_option)
                all_data.extend(platform_results)
                progress_bar.progress((idx + 1) / len(platforms_to_scrape))
        finally:
            driver.quit()

        status_text.text("Scraping Completed!")

        if all_data:
            df = pd.DataFrame(all_data)
            st.success(f"Found {len(df)} results across {len(platforms_to_scrape)} platforms!")
            st.dataframe(df, use_container_width=True)

            # Option to download CSV for your test submission
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download Results as CSV",
                data=csv,
                file_name=f"scraped_{keyword}_{days_option}days.csv",
                mime="text/csv"
            )
        else:
            st.info("No results found for this timframe, try increasing the No. of days")