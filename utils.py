import pandas as pd
import os
import time
import sys
import base64
import requests
from typing import Any, List, Dict, Optional
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from easyocr import Reader
# Import configuration constants
from config import TARGET_URL, TEMP_IMAGE_FILE, TRADES_EXCEL, CREDENTIALS_EXCEL


# Define the log file name
LOG_FILE_NAME = "bot_log.txt"

def log(message: str, trade_name: str = "SYSTEM", is_error: bool = False):
    """Prints and writes a timestamped message to a log file."""
    # Use YYYY-MM-DD HH:MM:SS format for better sorting and tracking
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    output = f"[{timestamp}][{trade_name}] {message}"

    # Write to log file (CRITICAL for scheduled tasks)
    try:
        # Use 'a' mode to append to the file, ensuring we don't overwrite history
        with open(LOG_FILE_NAME, 'w', encoding='utf-8') as f:
            f.write(output + '\n')
    except Exception as e:
        # If file writing fails, at least log to stderr (visible in Task Scheduler log)
        print(f"FATAL LOGGING ERROR: Failed to write to {LOG_FILE_NAME}: {e}", file=sys.stderr)

    # Print to console (for immediate feedback during manual/debug runs)
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

# Read all credentials from the first sheet of credentials.xlsx
def read_credentials() -> List[Dict[str, str]]:
    """
    Reads multiple username/password pairs from the first sheet of the Excel file.
    """
    required_cols = ['username', 'password']
    try:
        # Read the first sheet (or 'Sheet1' if it exists)
        df = pd.read_excel(CREDENTIALS_EXCEL, sheet_name=0,
                           dtype={required_cols[0]:str, 
                                  required_cols[1]:str}).dropna() 

        df.columns = [col.strip() for col in df.columns]

        if not all(col in df.columns for col in required_cols):
            log(f"ERROR: '{CREDENTIALS_EXCEL}' sheet is missing required columns.", is_error=True)
            return []

        credentials = df[required_cols].to_dict('records')
        log(f"Successfully loaded {len(credentials)} sets of credentials from {CREDENTIALS_EXCEL}.", "SYSTEM")
        return credentials

    except FileNotFoundError:
        log(f"ERROR: '{CREDENTIALS_EXCEL}' not found. Please create it.", is_error=True)
        return []
    except Exception as e:
        log(f"An error occurred while reading credentials: {e}", is_error=True)
        return []


# Read trade data from a specific sheet in trades.xlsx
def read_trade_data(username: str) -> List[Dict[str, Any]]:
    """
    Reads, validates, and sorts trade data from the sheet named after the username 
    in the TRADES_EXCEL file.
    """
    # Use the username as the sheet name
    sheet_name = username 
    
    try:
        # Read the specific sheet
        df = pd.read_excel(TRADES_EXCEL, sheet_name=sheet_name)
        
        # ... (Validation, cleaning, and sorting logic remains the same)
        df.columns = [col.strip() for col in df.columns]

        required_cols = ['Name', 'Price', 'Volume', 'Direction']
        if not all(col in df.columns for col in required_cols):
             log(f"ERROR: Trade sheet '{sheet_name}' is missing required columns.", is_error=True)
             return []

        # Vectorized Data Cleaning and Validation
        df['Name'] = df['Name'].astype(str).str.strip().str.upper()
        df['Direction'] = df['Direction'].astype(str).str.strip().str.title()
        
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0).astype(int)
        df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce').fillna(0).astype(int)

        valid_directions = ["Buy", "Sell"]
        df_valid = df[df['Direction'].isin(valid_directions) & (df['Name'].str.len() > 0)].copy()

        invalid_count = len(df) - len(df_valid)
        if invalid_count > 0:
            log(f"WARNING: Skipped {invalid_count} trade(s) in sheet '{sheet_name}'.", "SYSTEM", is_error=True)
        
        # Sorting Logic
        is_price_zero = df_valid['Price'] == 0
        is_volume_zero = df_valid['Volume'] == 0
        df_valid['Sort_Key'] = is_price_zero.astype(int) + is_volume_zero.astype(int)
        df_sorted = df_valid.sort_values(by=['Sort_Key', 'Name'], ascending=[False, True])
        
        trades = df_sorted[required_cols].to_dict('records')

        log(f"Successfully loaded and sorted {len(trades)} trade(s) from sheet '{sheet_name}'.", username)
        return trades

    except ValueError as ve:
        # Catch error if the sheet name is not found
        log(f"ERROR: Trade sheet '{sheet_name}' not found in {TRADES_EXCEL}. Ensure sheet name matches username exactly. Error: {ve}", is_error=True)
        return []
    except FileNotFoundError:
        log(f"ERROR: Trade file '{TRADES_EXCEL}' not found.", is_error=True)
        return []
    except Exception as e:
        log(f"An error occurred while reading trade data for {username}: {e}", is_error=True)
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