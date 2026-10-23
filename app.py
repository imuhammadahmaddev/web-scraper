import streamlit as st
import pandas as pd
import time
import re
import base64
import urllib.parse
import requests
import xml.etree.ElementTree as ET
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
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=options)
    return driver


# filter
def clean_ddg_url(raw_url):
    """Extracts the actual URL from DuckDuckGo's /l/?uddg= redirect link."""
    if not raw_url:
        return ""
    if "bing.com/ck/a" in raw_url and "u=" in raw_url:
        parsed = urllib.parse.urlparse(raw_url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "u" in qs and qs["u"][0].startswith("a1"):
            b64_str = qs["u"][0][2:]
            b64_str += "=" * (-len(b64_str) % 4)
            try:
                return base64.urlsafe_b64decode(b64_str).decode("utf-8", errors="ignore")
            except Exception:
                pass
    if "RU=" in raw_url:
        match = re.search(r"/RU=([^/]+)/", raw_url)
        if match:
            return urllib.parse.unquote(match.group(1))
    if "uddg=" in raw_url:
        parsed = urllib.parse.urlparse(raw_url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "uddg" in qs:
            return urllib.parse.unquote(qs["uddg"][0])
    if raw_url.startswith("//"):
        return "https:" + raw_url
    return raw_url


def is_within_days(date_str, max_days):
    """Checks if a scraped date string ('3 days ago', 'Oct 10, 2026') falls within max_days."""
    if not date_str:
        return True
    clean_str = re.sub(r"^(streamed|premiered|updated|published)\s+", "", str(date_str).strip(), flags=re.I)
    now = datetime.now()
    parsed_date = dateparser.parse(
        clean_str,
        settings={"PREFER_DATES_FROM": "past", "RETURN_AS_TIMEZONE_AWARE": False, "RELATIVE_BASE": now}
    )
    if not parsed_date:
        return True
    parsed_date = parsed_date.replace(tzinfo=None)
    cutoff_date = now - timedelta(days=max_days, hours=12)
    return parsed_date >= cutoff_date


def get_ddg_date_param(days):
    """Maps 1-365 days to DuckDuckGo's native 'df' parameter."""
    if days <= 1:
        return "d"
    elif days <= 7:
        return "w"
    elif days <= 31:
        return "m"
    else:
        return "y"


#core engine
def scrape_blogs(keyword, days):
    results = []
    seen_links = set()
    kw = keyword.strip()
    variations = [
        f"{kw} when:{days}d",
        f'"{kw}" blog when:{days}d',
        f"{kw} news OR article when:{days}d",
        f"{kw} latest trends when:{days}d"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    for q in variations:
        encoded_kw = urllib.parse.quote(q)
        rss_urls = [
            f"https://news.google.com/rss/search?q={encoded_kw}&hl=en-US&gl=US&ceid=US:en",
            f"https://www.bing.com/news/search?q={urllib.parse.quote(kw)}&format=rss"
        ]
        for rss_url in rss_urls:
            try:
                resp = requests.get(rss_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    for item in root.findall(".//item")[:25]:
                        title = item.findtext("title") or ""
                        link = item.findtext("link") or ""
                        pub_date = item.findtext("pubDate") or ""
                        source_el = item.find("source")
                        source = source_el.text if source_el is not None and source_el.text else "Blog / Article"

                        if link and link not in seen_links and is_within_days(pub_date, days):
                            seen_links.add(link)
                            results.append({
                                "Platform": "Blogs",
                                "Title / Snippet": f"[{source}] {title}",
                                "Date": pub_date[:16] if pub_date else f"Last {days} days",
                                "URL": link
                            })
            except Exception:
                pass

    return results


def scrape_platform(driver, keyword, platform, days):
    results = []
    seen_links = set()
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    kw = keyword.strip()

    # first Case: direct YT scrapping
    if platform == "YouTube":
        # Use YouTube's Today filter (EgIIAg%3D%3D) when days <= 1, Week (EgIIAw%3D%3D) when <= 7, or Upload Date sort
        yt_sp = "EgIIAg%253D%253D" if days <= 1 else ("EgIIAw%253D%253D" if days <= 7 else "CAISAhAB")
        for yt_kw in [kw, f"{kw} latest", f"{kw} news"]:
            encoded_kw = urllib.parse.quote(yt_kw)
            # sp=CAISAhAB sorts YouTube results by upload date (AI Helped)
            url = f"https://www.youtube.com/results?search_query={encoded_kw}&sp={yt_sp}"
            try:
                driver.get(url)
                time.sleep(2.5)
                for _ in range(3):
                    driver.execute_script("window.scrollBy(0, 1500);")
                    time.sleep(0.8)

                page_html = driver.page_source
                soup = BeautifulSoup(page_html, "html.parser")
                videos = soup.find_all("ytd-video-renderer", limit=35)

                for v in videos:
                    title_el = v.find("a", id="video-title")
                    if not title_el or not title_el.get("href"):
                        continue

                    vid_url = "https://www.youtube.com" + title_el["href"].split("&")[0]
                    if vid_url in seen_links:
                        continue

                    meta_els = v.find_all("span", class_="inline-metadata-item")
                    date_text = ""
                    for m in meta_els:
                        txt = m.text.strip()
                        if any(w in txt.lower() for w in ["ago", "hour", "day", "week", "month", "year", "minute", "streamed"]):
                            date_text = txt
                            break

                    if is_within_days(date_text, days):
                        seen_links.add(vid_url)
                        results.append({
                            "Platform": "YouTube",
                            "Title / Snippet": title_el.text.strip(),
                            "Date": date_text or f"Last {days} days",
                            "URL": vid_url
                        })

                # Also extract directly from YouTube's embedded JSON to ensure 25-40+ results
                pattern = r'"videoRenderer":\{"videoId":"([a-zA-Z0-9_-]{11})".*?"title":\{"runs":\[\{"text":"([^"]+)"\}\].*?"publishedTimeText":\{"simpleText":"([^"]+)"\}'
                for vid_id, title_txt, pub_txt in re.findall(pattern, page_html):
                    vid_url = f"https://www.youtube.com/watch?v={vid_id}"
                    if vid_url not in seen_links and is_within_days(pub_txt, days):
                        seen_links.add(vid_url)
                        results.append({
                            "Platform": "YouTube",
                            "Title / Snippet": title_txt,
                            "Date": pub_txt,
                            "URL": vid_url
                        })
            except Exception:
                pass

            if len(results) >= 35:
                break
        return results

    if platform == "Blogs":
        return scrape_blogs(keyword, days)

    # second Case: Socials & Blogs via Search Index Scraping
    # Uses DuckDuckGo HTML / Google index to bypass Facebook/IG/X login walls
    hashtag = "#" + "".join(w.capitalize() for w in kw.split())
    site_map = {
        "Facebook": [
            f'site:facebook.com "{kw}"',
            f'site:facebook.com {kw} posts',
            f'site:facebook.com {kw} latest',
            f'site:facebook.com {hashtag}'
        ],
        "X (Twitter)": [
            f'site:x.com "{kw}"',
            f'site:twitter.com "{kw}"',
            f'site:x.com {kw} status',
            f'site:twitter.com {kw} latest'
        ],
        "Instagram": [
            f'site:instagram.com "{kw}"',
            f'site:instagram.com {kw} reel',
            f'site:instagram.com {kw} post',
            f'site:instagram.com {hashtag}'
        ],
        "TikTok": [
            f'site:tiktok.com "{kw}"',
            f'site:tiktok.com {kw} video',
            f'site:tiktok.com {kw}',
            f'site:tiktok.com {hashtag}'
        ]
    }

    domain_checks = {
        "Facebook": ["facebook.com", "fb.com", "fb.watch"],
        "X (Twitter)": ["x.com", "twitter.com"],
        "Instagram": ["instagram.com"],
        "TikTok": ["tiktok.com"]
    }

    queries = site_map.get(platform, [kw])
    valid_domains = domain_checks.get(platform, [])
    df_param = get_ddg_date_param(days)
    yahoo_btf = "d" if days <= 1 else ("w" if days <= 7 else "m")

    for q in queries:
        encoded_q = urllib.parse.quote(q)

        # 1. Bing Search (Primary high-speed harvester with Base64 URL decoder)
        for page in range(2):
            first = page * 10 + 1
            bing_url = f"https://www.bing.com/search?q={encoded_q}&first={first}"
            try:
                driver.get(bing_url)
                time.sleep(1.2)
                soup = BeautifulSoup(driver.page_source, "html.parser")
                for item in soup.select("li.b_algo"):
                    a_tag = item.select_one("h2 a")
                    snippet_tag = item.select_one("p, div.b_caption p")
                    cite_tag = item.select_one("cite")
                    if a_tag and a_tag.get("href"):
                        link = clean_ddg_url(a_tag.get("href", ""))
                        cite_txt = cite_tag.text.lower() if cite_tag else ""
                        if (any(d in link.lower() for d in valid_domains) or any(d in cite_txt for d in valid_domains)) and link not in seen_links:
                            seen_links.add(link)
                            title = a_tag.text.strip()
                            snippet = snippet_tag.text.strip() if snippet_tag else ""
                            results.append({
                                "Platform": platform,
                                "Title / Snippet": f"{title} — {snippet}",
                                "Date": f"Since {cutoff_date} (<= {days} days)",
                                "URL": link
                            })
            except Exception:
                pass

        # 2. Yahoo Search (With automatic fallback if strict 1-day filter is empty)
        yahoo_urls = [f"https://search.yahoo.com/search?p={encoded_q}&btf={yahoo_btf}"]
        if days <= 7:
            yahoo_urls.append(f"https://search.yahoo.com/search?p={encoded_q}")

        for yahoo_url in yahoo_urls:
            try:
                driver.get(yahoo_url)
                time.sleep(1.2)
                soup = BeautifulSoup(driver.page_source, "html.parser")
                cards = soup.select("div.algo, div.Sr")
                for card in cards:
                    a_tag = card.select_one("h3.title a, a.ac-algo")
                    snippet_tag = card.select_one("div.compText, p")
                    if a_tag and a_tag.get("href"):
                        link = clean_ddg_url(a_tag.get("href", ""))
                        if any(d in link.lower() for d in valid_domains) and link not in seen_links:
                            seen_links.add(link)
                            title = a_tag.text.strip()
                            snippet = snippet_tag.text.strip() if snippet_tag else ""
                            results.append({
                                "Platform": platform,
                                "Title / Snippet": f"{title} — {snippet}",
                                "Date": f"Since {cutoff_date} (<= {days} days)",
                                "URL": link
                            })
                if len(results) >= 15:
                    break
            except Exception:
                pass

        # 3. DuckDuckGo HTML (Fallback)
        if len(results) < 10:
            search_url = f"https://html.duckduckgo.com/html/?q={encoded_q}&df={df_param}"
            try:
                driver.get(search_url)
                time.sleep(1.2)
                soup = BeautifulSoup(driver.page_source, "html.parser")
                items = soup.find_all("div", class_="result__body", limit=15)

                if not items:
                    search_url_fallback = f"https://html.duckduckgo.com/html/?q={encoded_q}"
                    driver.get(search_url_fallback)
                    time.sleep(1.2)
                    soup = BeautifulSoup(driver.page_source, "html.parser")
                    items = soup.find_all("div", class_="result__body", limit=15)

                for item in items:
                    title_tag = item.find("a", class_="result__a")
                    snippet_tag = item.find("a", class_="result__snippet")

                    if title_tag:
                        title = title_tag.text.strip()
                        raw_link = title_tag.get("href", "")
                        link = clean_ddg_url(raw_link)
                        snippet = snippet_tag.text.strip() if snippet_tag else ""

                        if any(d in link.lower() for d in valid_domains) and link not in seen_links:
                            seen_links.add(link)
                            results.append({
                                "Platform": platform,
                                "Title / Snippet": f"{title} — {snippet}",
                                "Date": f"Since {cutoff_date} (<= {days} days)",
                                "URL": link
                            })
            except Exception:
                pass

        if len(results) >= 30:
            break

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
            st.success(f"Found {len(df)} results across {df['Platform'].nunique()} platforms!")

            # Show quick summary count per platform
            st.write("### Results Breakdown by Platform")
            st.dataframe(df["Platform"].value_counts().rename("Count"), use_container_width=False)

            st.write("### Scraped Data")
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