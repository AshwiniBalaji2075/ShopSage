# scraping_functions.py
import re
import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urljoin  # NEW

CROMA_BASE = "https://www.croma.com"
FLIPKART_BASE = "https://www.flipkart.com"

def clean_price(price_str):
    """Extract numerical value from price string"""
    if not price_str:
        return 0.0
    # Keep digits and dot; commas/symbols removed
    cleaned = re.sub(r'[^\d.]', '', price_str)
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0

def make_absolute(url_value: str, base: str) -> str:
    """Make sure URL is absolute."""
    if not url_value:
        return ""
    return urljoin(base, url_value)

def scrape_croma(product_name):
    """Scrape Croma for product price and link using Selenium"""
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )

        search_q = product_name.replace(' ', '%20')
        search_url = f"{CROMA_BASE}/searchB?q={search_q}%3Arelevance&text={search_q}"
        driver.get(search_url)
        time.sleep(3)

        # -------------------------------
        # Product Name
        # -------------------------------
        name = None
        try:
            name = driver.find_element(By.CSS_SELECTOR, "h3.product-title a").text.strip()
        except Exception:
            try:
                name = driver.find_element(By.CSS_SELECTOR, "h3.product-title").text.strip()
            except Exception:
                name = "Product name not found"

        # -------------------------------
        # Product Price
        # -------------------------------
        price = 0.0
        try:
            price_text = driver.find_element(By.CSS_SELECTOR, "span.amount").text
            price = clean_price(price_text)
        except Exception:
            try:
                price_text = driver.find_element(By.CSS_SELECTOR, 'span[data-testid="price"]').text
                price = clean_price(price_text)
            except Exception:
                price = 0.0

        # -------------------------------
        # Product URL (important fix)
        # -------------------------------
        product_href = None
        try:
            # Croma product link is usually inside h3.product-title > a
            el = driver.find_element(By.CSS_SELECTOR, "h3.product-title a")
            product_href = el.get_attribute("href")
        except Exception:
            pass

        product_url = make_absolute(product_href, CROMA_BASE) if product_href else ""

        # Debug print
        print("DEBUG Croma URL:", product_url)

        return name, price, product_url

    except Exception as e:
        print(f"Error scraping Croma: {e}")
        return None, None, None
    finally:
        if driver:
            driver.quit()


def scrape_flipkart(product_name):
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )

        search_q = product_name.replace(' ', '+')
        search_url = f"{FLIPKART_BASE}/search?q={search_q}"
        driver.get(search_url)
        time.sleep(3)

        name = driver.find_element(By.CSS_SELECTOR, 'div.KzDlHZ').text
        price = clean_price(driver.find_element(By.CSS_SELECTOR, 'div.Nx9bqj').text)
        href = driver.find_element(By.CSS_SELECTOR, 'a.CGtC98').get_attribute('href')

        product_url = make_absolute(href, FLIPKART_BASE)

        return name, price, product_url

    except Exception as e:
        print(f"Flipkart Scraping Error: {str(e)}")
        return None, None, None
    finally:
        if driver:
            driver.quit()
