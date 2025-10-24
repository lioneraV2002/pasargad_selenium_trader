import pandas as pd
import os
import time
import sys
import csv
import base64
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from easyocr import Reader



# Import configuration constants
from config import TARGET_URL, TEMP_IMAGE_FILE


def log(message: str, trade_name: str = "SYSTEM", is_error: bool = False):
    """Prints a timestamped message."""
    timestamp = time.strftime('%H:%M:%S')
    output = f"[{timestamp}][{trade_name}] {message}"
    if is_error:
        print(output, file=sys.stderr)
    else:
        print(output)

def setup_webdriver() -> Optional[webdriver.Chrome]:
    """Initializes and returns a configured Chrome WebDriver."""
    log("Setting up WebDriver...")
    try:
        chrome_options = Options()
        chrome_options.add_argument("--start-maximized")
                
        driver = webdriver.Chrome(options=chrome_options)        
        
        return driver
    except WebDriverException as e:
        log(f"FATAL WebDriver Setup Error: {e}", is_error=True)
        return None

def read_credentials(filename: str) -> Tuple[str, str]:
    """Reads username and password from the first data row of the CSV file."""
    try:
        with open(filename, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            next(reader) # Skip header row
            data = next(reader)
            if len(data) >= 2:
                return data[0].strip(), data[1].strip()
            else:
                log(f"ERROR: '{filename}' format is incorrect.", is_error=True)
                return "", ""
    except (FileNotFoundError, StopIteration):
        log(f"ERROR: '{filename}' not found or empty.", is_error=True)
        return "", ""
    except Exception as e:
        log(f"An error occurred while reading credentials: {e}", is_error=True)
        return "", ""




def read_trade_data(filename: str) -> List[Dict]:
    """
    Reads, validates, and sorts trade data from the CSV file using pandas for superior speed
    and efficiency.
    
    Sorting Priority:
    1. Price=0 AND Volume=0 (Sort Key = 2)
    2. Price=0 OR Volume=0 (Sort Key = 1)
    3. Neither is 0 (Sort Key = 0)
    """
    try:
        # Read CSV using pandas (much faster than csv module)
        df = pd.read_csv(filename)
        
        # Standardize column names (strip whitespace)
        df.columns = [col.strip() for col in df.columns]

        required_cols = ['Name', 'Price', 'Volume', 'Direction']
        if not all(col in df.columns for col in required_cols):
             log("ERROR: Trade CSV is missing required columns (Name, Price, Volume, Direction).", is_error=True)
             return []

        # Vectorized Data Cleaning and Validation
        df['Name'] = df['Name'].astype(str).str.strip().str.upper()
        df['Direction'] = df['Direction'].astype(str).str.strip().str.title()
        
        # Handle Price and Volume: Convert to numeric, coercing errors (like non-digit strings) to NaN, then filling NaN with 0.
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0).astype(int)
        df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce').fillna(0).astype(int)

        # Filter for valid data only
        valid_directions = ["Buy", "Sell"]
        df_valid = df[df['Direction'].isin(valid_directions) & (df['Name'].str.len() > 0)].copy()

        invalid_count = len(df) - len(df_valid)
        if invalid_count > 0:
            log(f"WARNING: Skipped {invalid_count} trade(s) due to invalid 'Direction' or empty 'Name'.", "SYSTEM", is_error=True)
        
        #  4. IMPLEMENT CUSTOM SORTING LOGIC 
        
        # Calculate a numerical sort key: the sum of boolean masks (True=1, False=0)
        is_price_zero = df_valid['Price'] == 0
        is_volume_zero = df_valid['Volume'] == 0
        
        df_valid['Sort_Key'] = is_price_zero.astype(int) + is_volume_zero.astype(int)
        
        # Sort the trades: highest Sort_Key first (descending). Use Name as secondary stability sort.
        df_sorted = df_valid.sort_values(by=['Sort_Key', 'Name'], ascending=[False, True])
        
        # Convert the cleaned, validated, and sorted DataFrame back to a list of dictionaries
        trades = df_sorted[required_cols].to_dict('records')

        log(f"Successfully loaded and sorted {len(trades)} trade(s) using pandas.", "SYSTEM")
        return trades

    except FileNotFoundError:
        log(f"ERROR: '{filename}' not found. Please create it.", is_error=True)
        return []
    except Exception as e:
        # Catch errors potentially from pandas not finding columns or files
        log(f"An error occurred while reading {filename} with pandas: {e}", is_error=True)
        return []
    

def ocr_captcha_image(filepath: str) -> str:
    """Uses easyocr to read text from the captcha image file."""
    try:
        # Initialize Reader once (it's resource-intensive)
        reader = Reader(['en'])
        result = reader.readtext(image=filepath, allowlist='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')

        # Filter results and combine text
        if result:
            # Result format is [(bbox, text, confidence)]
            # We assume the CAPTCHA is a single block of text
            captcha_text = "".join(str(r[1]).strip() for r in result if r[2] > 0.5) # Only take high confidence
            return captcha_text

        log("OCR failed to find recognizable text with high confidence.", is_error=True)
        return ""
    except Exception as e:
        log(f"OCR processing error: {e}", is_error=True)
        return ""
    

def process_and_solve_captcha(driver, img_xpath: str) -> str:
    """Downloads, saves, OCRs, and cleans up the CAPTCHA image."""
    image_bytes = None
    try:
        captcha_img = driver.find_element("xpath", img_xpath)
        image_src = captcha_img.get_attribute('src')
        log(f"Captcha image source retrieved: {image_src[:50]}...")

        if image_src.startswith('data:'):
            # Base64 Data URI
            comma_index = image_src.find(',')
            if comma_index != -1:
                base64_data = image_src[comma_index + 1:]
                image_bytes = base64.b64decode(base64_data)
                log("Image was Base64 encoded; decoded successfully.")
        else:
            # Standard URL
            image_url = urljoin(TARGET_URL, image_src) if image_src.startswith('/') else image_src
            response = requests.get(image_url, stream=True, timeout=10)
            response.raise_for_status()
            image_bytes = response.content
            log("Image downloaded via requests.")

        if image_bytes:
            with open(TEMP_IMAGE_FILE, "wb") as f:
                f.write(image_bytes)
            log(f"Captcha image SAVED to temporary file: {TEMP_IMAGE_FILE}")

            captcha_text = ocr_captcha_image(TEMP_IMAGE_FILE)
            log(f"OCR Result: '{captcha_text}'")
            return captcha_text

    except NoSuchElementException:
        log(f"ERROR: Could not find Captcha image using XPath: {img_xpath}", is_error=True)
    except Exception as e:
        log(f"An unexpected error occurred during CAPTCHA processing: {e}", is_error=True)
    finally:
        if os.path.exists(TEMP_IMAGE_FILE):
            os.remove(TEMP_IMAGE_FILE)
            log(f"Cleaned up temporary file: {TEMP_IMAGE_FILE}")
            
    return ""