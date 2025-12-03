import time
from typing import Dict, Any, List, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from datetime import datetime, time as dt_time, timedelta 
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# Import utilities and configuration
from utils import log, setup_webdriver, read_trade_data, process_and_solve_captcha
from config import (
    TARGET_URL, LOGIN_ID_USERNAME, LOGIN_ID_PASSWORD, CAPTCHA_IMAGE,
    CAPTCHA_INPUT, LOGIN_BUTTON_XPATH, OPEN_MODAL_BUTTON_XPATH, SEQUENTIAL_MODAL_BASE_XPATH,
    MODAL_XPATHS_RELATIVE, BULK_SELECTION_BUTTON, BULK_ORDER_AND_REMOVE, DRAFTS_SECTION_TAB,
    LOGOUT_BUTTON, CLOSE_BUTTON_XPATH, MODAL_XPATH
)


class StockTrader:
    """
    Manages the trading process with support for driver session reuse across multiple users
    within a single process.
    """
    
    @staticmethod
    def wait_until_market_open(target_hour=8, target_minute=45): # Changed default to 8:44 as requested
        """
        Calculates the required sleep duration until the next occurrence of the target time
        (defaulting to 08:44:00 AM) and pauses the script. Includes a 10-second grace period.
        """
        now = datetime.now()
        # The user requested 8:44 AM as the synchronization point.
        target_time_dt = dt_time(target_hour, target_minute, 0)
        target_time_today = datetime.combine(now.date(), target_time_dt)
        grace_period = timedelta(seconds=60) 

        # Check if we are past the target time + grace period for today
        if now > target_time_today + grace_period:
            # Case 1: Past target time AND past the grace period -> Wait until tomorrow
            target_datetime = datetime.combine(now.date() + timedelta(days=1), target_time_dt)
            log(f"Target time and grace period passed. Waiting until tomorrow ({target_datetime.strftime('%Y-%m-%d %H:%M:%S')}).", "TIMER")
            
            sleep_duration = (target_datetime - now).total_seconds()
            log(f"... Waiting for {int(sleep_duration)} seconds.", "TIMER")
            time.sleep(sleep_duration)

        elif now >= target_time_today:
            # Case 2: Past target time but WITHIN the grace period -> Proceed immediately
            log(f"Target time ({target_time_dt}) passed, but within grace period. Proceeding immediately.", "TIMER")
            
        else:
            # Case 3: Still before target time today -> Wait until target time today
            target_datetime = target_time_today
            log(f"Waiting until target time today ({target_datetime.strftime('%H:%M:%S')}).", "TIMER")

            sleep_duration = (target_datetime - now).total_seconds()
            log(f"... Waiting for {int(sleep_duration)} seconds.", "TIMER")
            time.sleep(sleep_duration)

        log("Wait complete. Proceeding with execution phase.", "TIMER")


    def __init__(self):
        """Initializes without user info, designed to be configured later."""
        self.driver: Optional[webdriver.Chrome] = None
        self.trades: List[Dict[str, Any]] = []
        self.username: str = ""
        self.password: str = ""
        self.log_tag: str = "TRADER"
        self.is_logged_in: bool = False

    def set_user_credentials(self, username: str, password: str, log_tag: str):
        """Updates the instance with the new user's credentials and logging tag."""
        self.username = username
        self.password = password
        self.log_tag = log_tag
        self.trades = [] # Clear previous user's data
        self.is_logged_in = False
    
    def initialize_data(self) -> bool:
        """Loads trade instructions using the current username."""
        self.trades = read_trade_data(self.username)
        if not self.trades:
            log(f"No valid trades loaded for user {self.username}. Initialization failed.", self.log_tag, is_error=True)
            return False
        
        log(f"Loaded {len(self.trades)} trades successfully.", self.log_tag)
        return True

    def _find_modal_element(self, xpath_key: str):
        """Helper to find an element within the specific modal."""
        if not self.driver:
            raise WebDriverException(f"Driver not initialized in _find_modal_element.")
        
        relative_xpath = MODAL_XPATHS_RELATIVE[xpath_key]
        full_xpath = f"{SEQUENTIAL_MODAL_BASE_XPATH}{relative_xpath[1:]}"
        return self.driver.find_element(By.XPATH, full_xpath)


    def _attempt_login(self) -> bool:
        """Performs the login sequence. Assumes driver is on the login page."""
        if not self.driver: return False
        
        try:
            # Input Credentials and CAPTCHA
            self.driver.find_element(By.ID, LOGIN_ID_USERNAME).clear()
            self.driver.find_element(By.ID, LOGIN_ID_PASSWORD).clear()
            self.driver.find_element(By.ID, LOGIN_ID_USERNAME).send_keys(self.username)
            self.driver.find_element(By.ID, LOGIN_ID_PASSWORD).send_keys(self.password)
            
            captcha_text = process_and_solve_captcha(self.driver, CAPTCHA_IMAGE) 
            if not captcha_text: return False
                
            self.driver.find_element(By.XPATH, CAPTCHA_INPUT).send_keys(captcha_text)
            self.driver.find_element(By.XPATH, LOGIN_BUTTON_XPATH).click()
            
            # Wait for dashboard load (or blocking modal)
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.XPATH, OPEN_MODAL_BUTTON_XPATH))
            )
            return True
        except TimeoutException:
            # Check for the blocking password modal instead of dashboard
            try:
                self.check_and_close_password_modal()
                return True # Login successful but blocked by modal
            except:
                return False # Login failed
        except Exception as e:
            log(f"Unexpected error during login attempt: {e}", self.log_tag, is_error=True)
            return False


    def initialize_session(self) -> bool:
        """
        Initializes the driver if necessary (first user in batch) and logs in
        the current user (for all users in batch).
        """
        if not self.username or not self.password:
             log("Credentials not set. Cannot initialize session.", self.log_tag, is_error=True)
             return False

        if not self.driver:
            # Only set up the driver if it's the first user in the batch
            self.driver = setup_webdriver()
            if not self.driver: return False

        # Go to login page (essential if reusing the driver and logged out previously)
        self.driver.get(TARGET_URL)
        WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.XPATH, CAPTCHA_INPUT))
        )

        for attempt in range(5):
            if self._attempt_login():
                self.is_logged_in = True
                self.check_and_close_password_modal()
                log("Login successful.", self.log_tag)
                return True
            log(f"Login attempt {attempt + 1} failed. Retrying...", self.log_tag, is_error=True)
            time.sleep(5)
            
        log("All login attempts failed.", self.log_tag, is_error=True)
        return False


    def safe_logout(self):
        """Logs out the current user, but keeps the driver open for the next user."""
        if self.driver and self.is_logged_in:
            try:
                # The user requested logging out after each task.
                self.driver.find_element(By.XPATH, LOGOUT_BUTTON).click()
                self.is_logged_in = False
                log("Logged out successfully, keeping driver alive.", self.log_tag)
            except Exception:
                log("WARNING: Could not find or click LOGOUT button.", self.log_tag)
            time.sleep(1) # Wait for logout redirect

    def quit_driver(self):
        """Quits the WebDriver session permanently."""
        if self.driver:
            log("Quitting WebDriver.", self.log_tag)
            self.driver.quit()
            self.driver = None
        self.is_logged_in = False


    def check_and_close_password_modal(self):
        """Checks for the presence of the change password modal and closes it."""
        try:
            if self.driver:
                WebDriverWait(self.driver, 1).until(
                    EC.presence_of_element_located((By.XPATH, MODAL_XPATH))
                )
                close_button = WebDriverWait(self.driver, 1).until(
                    EC.element_to_be_clickable((By.XPATH, CLOSE_BUTTON_XPATH))
                )
                close_button.click()
                WebDriverWait(self.driver, 1).until(
                    EC.invisibility_of_element_located((By.XPATH, MODAL_XPATH))
                )
                log("Modal successfully closed.", self.log_tag)
        except TimeoutException:
            pass # Modal not found
        except Exception as e:
            log(f"WARNING: Error closing modal: {e}", self.log_tag)
            
            
    def _create_single_draft(self, trade_data: Dict[str, Any], trade_index: int):
        """Helper to create one draft trade."""
        trade_name = f"{trade_data['Name']}-{trade_index}"
        try:
            self.driver.find_element(By.XPATH, OPEN_MODAL_BUTTON_XPATH).click()
            time.sleep(1) 
            
            # Select Trade Direction (Buy/Sell)
            direction = trade_data['Direction']
            direction_xpath_key = "BUY_BUTTON" if direction == "Buy" else "SELL_BUTTON"
            self._find_modal_element(direction_xpath_key).click()
            
            # Simple stock entry (assuming configuration is set)
            search_input = self._find_modal_element("SEARCH_INPUT")
            search_input.send_keys(trade_data['Name'])
            time.sleep(1)
            search_input.send_keys(Keys.ENTER)
            time.sleep(1)

            # Set Volume
            volume = trade_data['Volume']
            if volume == 0:
                self._find_modal_element("MAX_VOLUME_CLICK").click()
            else:
                volume_input = self._find_modal_element("VOLUME_INPUT")
                volume_input.clear()
                volume_input.send_keys(str(volume))
            
            # Drafting the order
            self._find_modal_element('DRAFT_SELECTION').click()
            time.sleep(0.1) 
            self._find_modal_element('DRAFT_BUTTON').click()
            log(f"Order **Drafted** for {trade_data['Name']}. Trade name: {trade_name}", self.log_tag)
            
        except NoSuchElementException as e:
            log(f"ERROR: Element missing during draft creation. {e}", self.log_tag, is_error=True)
        except Exception as e:
            log(f"An unexpected error occurred during draft creation. {e}", self.log_tag, is_error=True)
        finally:
            # Close Modal
            try:
                self._find_modal_element("CLOSE_MODAL_BUTTON").click()
                time.sleep(0.1) 
            except:
                log(f"WARNING: Failed to close the modal. Trade name: {trade_name}", self.log_tag)


    # --- PHASE 1 Method (Replaces draft_workflow) ---
    def draft_single_task(self) -> bool:
        """
        Loads trades for the current user and creates all drafts.
        The driver must be initialized and logged in before calling this.
        """
        if not self.initialize_data():
            return False
            
        log(f"Loaded {len(self.trades)} trades for drafting.", self.log_tag)

        try:
            for i, trade in enumerate(self.trades):
                self._create_single_draft(trade, i + 1)
                
            return True
        except Exception as e:
            log(f"FATAL ERROR during trade drafting loop: {e}", self.log_tag, is_error=True)
            return False


    # --- PHASE 2 Method (Replaces execute_bulk_trades/execute_workflow) ---
    def execute_bulk_session(self):
        """
        Navigates to the drafts section, selects all, and submits the bulk order.
        The driver must be initialized and logged in before calling this.
        """
        log("Starting bulk draft execution (Final Submit Phase).", self.log_tag)
        if not self.driver:
            log("ERROR: WebDriver not available for draft execution.", self.log_tag, is_error=False)
            return False

        try:
            # 1. Navigate to Drafts
            self.driver.find_element(By.XPATH, DRAFTS_SECTION_TAB).click()
            time.sleep(1)
            
            # 2. Select All Drafts
            self.driver.find_element(By.XPATH, BULK_SELECTION_BUTTON).click()
            log("All available drafts selected.", self.log_tag)
            
            # The wait point is handled by the orchestrator workers before this batch starts.
            
            # 3. Find and click the Bulk Order/Remove button (submits all selected)
            bulk_submit_button = self.driver.find_element(By.XPATH, BULK_ORDER_AND_REMOVE)
            bulk_submit_button.click()
            time.sleep(5) 

            log("Bulk Order Submission initiated. All selected drafts sent to market.", self.log_tag)
            return True

        except NoSuchElementException:
            log("ERROR: Could not find bulk order elements. Check XPATH configurations.", self.log_tag, is_error=True)
            return False
        except Exception as e:
            log(f"An unexpected error occurred during bulk execution: {e}", self.log_tag, is_error=True)
            return False