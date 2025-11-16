import time
from typing import Dict, Any, List, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from datetime import datetime, time as dt_time, timedelta 
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Import utilities and configuration
from utils import log, setup_webdriver, read_trade_data, process_and_solve_captcha
from config import (
    TARGET_URL, LOGIN_ID_USERNAME, LOGIN_ID_PASSWORD, CAPTCHA_IMAGE,
    CAPTCHA_INPUT, LOGIN_BUTTON_XPATH, OPEN_MODAL_BUTTON_XPATH, SEQUENTIAL_MODAL_BASE_XPATH,
    MODAL_XPATHS_RELATIVE, BULK_SELECTION_BUTTON, BULK_ORDER_AND_REMOVE, DRAFTS_SECTION_TAB,
    LOGOUT_BUTTON, CLOSE_BUTTON_XPATH, MODAL_XPATH
)




def wait_until_market_open(target_hour=8, target_minute=45):
    """
    Calculates the required sleep duration until the next occurrence of the target time
    (defaulting to 08:45:00 AM) and pauses the script. Includes a 10-second grace period.
    """
    now = datetime.now()
    grace_period = timedelta(seconds=10) # 10 second buffer

    # Define today's target time
    target_time_today = datetime.combine(now.date(), dt_time(target_hour, target_minute, 0))

    if now > target_time_today + grace_period:
        # Case 1: Past target time AND past the grace period -> Wait until tomorrow
        target_datetime = datetime.combine(now.date() + timedelta(days=1), dt_time(target_hour, target_minute, 0))
        log(f"Target time and grace period passed. Waiting until tomorrow ({target_datetime.strftime('%H:%M:%S')}).", "TIMER")
        
        sleep_duration = (target_datetime - now).total_seconds()
        log(f"... Waiting for {int(sleep_duration)} seconds.", "TIMER")
        time.sleep(sleep_duration)

    elif now >= target_time_today:
        # Case 2: Past target time but WITHIN the 5-second grace period -> Proceed immediately
        sleep_duration = 0
        log("Target time passed, but within 5-second grace period. Proceeding immediately.", "TIMER")
        # No actual sleep needed
        
    else:
        # Case 3: Still before target time today -> Wait until target time today
        target_datetime = target_time_today
        log(f"Waiting until target time today ({target_datetime.strftime('%H:%M:%S')}).", "TIMER")

        sleep_duration = (target_datetime - now).total_seconds()
        log(f"... Waiting for {int(sleep_duration)} seconds.", "TIMER")
        time.sleep(sleep_duration)

    log("Wait complete. Proceeding with bulk order submission.", "TIMER")




class StockTrader:
    """Manages the sequential, end-to-end trading automation process using a single WebDriver session."""
    def __init__(self, username: str, password: str, log_tag: str):
        self.driver: Optional[webdriver.Chrome] = None  # Re-introduced single driver
        self.trades: List[Dict[str, Any]] = []
        self.username: str = username
        self.password: str = password        
        # Use username as the primary log tag for easy multi-process tracking
        self.log_tag: str = log_tag

    def initialize_data(self) -> bool:
            """Loads trade instructions using the username to find the correct file."""
            # read trades related to username given
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


    def login(self) -> bool:
        """Performs the full login sequence using the single driver instance."""
        if not self.driver:
            return False

        try:

            # Input Credentials and CAPTCHA
            self.driver.find_element(By.ID, LOGIN_ID_USERNAME).clear()
            self.driver.find_element(By.ID, LOGIN_ID_PASSWORD).clear()

            self.driver.find_element(By.ID, LOGIN_ID_USERNAME).send_keys(self.username)
            self.driver.find_element(By.ID, LOGIN_ID_PASSWORD).send_keys(self.password)
            
            
            # Process CAPTCHA
            # NOTE: Assuming process_and_solve_captcha now accepts just driver and xpath, 
            # and manages temporary files internally if necessary (or uses bytes).
            captcha_text = process_and_solve_captcha(self.driver, CAPTCHA_IMAGE) 
            if not captcha_text:
                log("Failed to solve CAPTCHA. Login aborted.", is_error=True)
                return False
            self.driver.find_element(By.XPATH, CAPTCHA_INPUT).send_keys(captcha_text)
            
            
            log("Credentials and CAPTCHA entered.")
            
            # Click Login
            self.driver.find_element(By.XPATH, LOGIN_BUTTON_XPATH).click()
            log("Attempted login. Waiting for dashboard load (10s)...")
            
            # Wait 20 seconds ONLY for the main dashboard button
            wait = WebDriverWait(self.driver, 20)
            wait.until(
                EC.presence_of_element_located((By.XPATH, OPEN_MODAL_BUTTON_XPATH))
            )
            
            # If we get here, the button was found. Login is successful.
            log("Dashboard loaded successfully.", self.log_tag)
            return True

        except TimeoutException:
            # This catches if the dashboard button *didn't* appear in 20 seconds.
            # NOW we check if the password modal is the reason.
            log("Dashboard button not found. Checking for password modal...", self.log_tag)
            
            try:
                self.check_and_close_password_modal()
                # We still return True, as the login was successful, just blocked by the modal.
                return True
                
            except TimeoutException:
                # If we get *here*, the dashboard button failed AND the modal failed.
                # This is a true login failure.
                log("Login failed: Neither dashboard nor modal found. Check credentials/CAPTCHA/URL.", self.log_tag, is_error=True)
                return False
                
        except Exception as e:
            log(f"An unexpected error occurred during login wait: {e}", self.log_tag, is_error=True)
            return False
        
        
    def create_draft(self, trade_data: Dict[str, Any], trade_index: int):
        """Executes a single trade using the established, single driver session."""
        trade_name = f"{trade_data['Name']}-{trade_index}"
        log(f"Trade execution started. Trade name: {trade_name}", self.log_tag)
        
        if not self.driver:
            log("ERROR: WebDriver not available for trade execution. Trade name: {trade_name}", self.log_tag, is_error=True)
            return

        try:
            # Open the trade modal (the button must be present after login)
            self.driver.find_element(By.XPATH, OPEN_MODAL_BUTTON_XPATH).click()
            time.sleep(0.5) 
        
            
            # Select Trade Direction (Buy/Sell)
            direction = trade_data['Direction']
            direction_xpath_key = "BUY_BUTTON" if direction == "Buy" else "SELL_BUTTON"
            self._find_modal_element(direction_xpath_key).click()
            log(f"Direction set to: {direction}. Trade name: {trade_name}", self.log_tag)

            # Search Stock Name and Select
            search_input = self._find_modal_element("SEARCH_INPUT")
            search_input.send_keys(trade_data['Name'])
            
            time.sleep(1)
            # check if the search result is out
            self._find_modal_element("SEARCH_RESULT_DIV")
            log(f"Search result element found. Trade name: {trade_name}", self.log_tag)                        
        
            search_input.send_keys(Keys.ENTER)
            log(f"Stock '{trade_data['Name']}' selected. Trade name: {trade_name}", self.log_tag)
            time.sleep(1) 

            # Set Volume
            volume = trade_data['Volume']
            if volume == 0:
                self._find_modal_element("MAX_VOLUME_CLICK").click()
                log("Volume set to MAX. Trade name: {trade_name}", self.log_tag)
            else:
                volume_input = self._find_modal_element("VOLUME_INPUT")
                volume_input.clear()
                volume_input.send_keys(str(volume))
                log(f"Custom volume entered: {volume}. Trade name: {trade_name}", self.log_tag)
            
            time.sleep(0.1) 
            
            # Set Price
            price = trade_data['Price']
            if price == 0:
                self._find_modal_element("LOCK_PRICE_BUTTON").click()
                log(f"Price set to Best Bid/Ask. Trade name: {trade_name}", self.log_tag)
            else:
                price_input = self._find_modal_element("PRICE_INPUT")
                price_input.clear()
                price_input.send_keys(str(price))
                log(f"Custom price entered: {price}. Trade name: {trade_name}", self.log_tag)

            time.sleep(0.1)            

            # Draft order
            self._find_modal_element('DRAFT_SELECTION').click()
            
            time.sleep(0.1) 
            
            self._find_modal_element('DRAFT_BUTTON').click()
            log(f"Order **Drafted** for {direction} {trade_data['Name']}. Trade name: {trade_name}", self.log_tag)
            

            
        except NoSuchElementException as e:
            log(f"ERROR: Element missing during trade execution. Trade name: {trade_name}.\n Error: {e}", self.log_tag, is_error=True)
        except Exception as e:
            log(f"An unexpected error occurred during trade execution. Trade name: {trade_name}.\n Error: {e}", self.log_tag, is_error=True)
        finally:
            # Close Modal
            try:
                self._find_modal_element("CLOSE_MODAL_BUTTON").click()
                time.sleep(0.1)             
                log(f"Modal closed. Trade name: {trade_name}", self.log_tag)
            except:
                log(f"WARNING: Failed to close the modal. Trade name: {trade_name}", self.log_tag, is_error=True)

    def execute_drafts(self):
        """
        Navigates to the drafts section, selects all, and submits the bulk order.
        Assumes the driver is on the main dashboard page after drafting.
        """
        log("Starting bulk draft execution.", "SYSTEM")
        if not self.driver:
            log("ERROR: WebDriver not available for draft execution.", "SYSTEM", is_error=True)
            return

        try:
            
            self.driver.find_element(By.XPATH, DRAFTS_SECTION_TAB).click()
            log("Clicked on drafts section tab.", "SYSTEM")
            
            time.sleep(1)
            # Click the Bulk Selection button/element
            # This action is assumed to open the list of drafts AND select them all.
            self.driver.find_element(By.XPATH, BULK_SELECTION_BUTTON).click()
            log("All available drafts selected.", "SYSTEM")

            # wait for market to open
            wait_until_market_open()
            
            # Find and click the Bulk Order/Remove button (which submits all selected)
            # This is the final step to move drafts to active orders.
            bulk_submit_button = self.driver.find_element(By.XPATH, BULK_ORDER_AND_REMOVE)
            bulk_submit_button.click()
            time.sleep(10)

            log("Bulk Order Submission initiated. All selected drafts sent to market.", "SYSTEM")
             # Wait for the server to process the bulk request

            log("Bulk draft execution completed successfully.", "SYSTEM")

        except NoSuchElementException:
            log("ERROR: Could not find bulk order elements. Check XPATH configurations.", "SYSTEM", is_error=True)
        except Exception as e:
            log(f"An unexpected error occurred during bulk execution: {e}", "SYSTEM", is_error=True)
            
        
        
    def check_and_close_password_modal(self):
        """
        Checks for the presence of the change password modal and closes it 
        if it is present by clicking the close button.
        """
        
        log("\nChecking for Change Password Modal...", self.log_tag)

        try:
            if self.driver:
                # Wait up to 1 seconds for the modal element to be present
                WebDriverWait(self.driver, 1).until(
                    EC.presence_of_element_located((By.XPATH, MODAL_XPATH))
                )
                
                log("Modal found. Attempting to close it.", self.log_tag)
                
                try:
                    # Wait up to 5 seconds for the close button to be clickable
                    close_button = WebDriverWait(self.driver, 1).until(
                        EC.element_to_be_clickable((By.XPATH, CLOSE_BUTTON_XPATH))
                    )
                    
                    # Click the close button
                    close_button.click()
                    log("Successfully clicked the modal close button.", self.log_tag)
                    
                    # Optional: Wait for the modal to disappear to confirm closure
                    WebDriverWait(self.driver, 1).until(
                        EC.invisibility_of_element_located((By.XPATH, MODAL_XPATH))
                    )
                    log("Modal successfully closed and disappeared.", self.log_tag)
                    
                except TimeoutException:
                    log("Error: Modal close button was not clickable within 1 seconds.", self.log_tag, is_error=True)
                except NoSuchElementException:
                    log("Error: Modal element was present, but the close button was not found.", self.log_tag, is_error=True)
                    
        except TimeoutException:
            log("Modal not found within 1 seconds. Assuming it did not appear or has already been closed.", self.log_tag, is_error=True)
        except Exception as e:
            log(f"An unexpected error occurred during modal check: {e}", self.log_tag, is_error=True)
    
    
    def run_workflow(self):
        """The main orchestration method for the sequential trading workflow."""
        log("Starting workflow.", self.log_tag)

        if not self.initialize_data():
            return

        self.driver = setup_webdriver() # Initialize the single driver

        if not self.driver:
            return

        self.driver.get(TARGET_URL)
        log(f"Navigated to {TARGET_URL}.", self.log_tag)
        
        time.sleep(5)
        
        
        for attempt in range(5):
            if self.login():
                break
            log(f"Login attempt {attempt + 1} failed. Retrying...", self.log_tag, is_error=True)
            time.sleep(5)
        else:
            log("All login attempts failed. Exiting.", self.log_tag, is_error=True)
            if self.driver: self.driver.quit()
            return

        log("Login successful: Dashboard loaded.", self.log_tag)
            
        try:
            # checking for password change modal
            self.check_and_close_password_modal()
            
            log("Starting sequential trade draft creation loop.", self.log_tag)

            start_time = time.time()

            # Sequential loop replaces the ThreadPoolExecutor
            for i, trade in enumerate(self.trades):
                log(f"--- Processing Trade {i + 1}/{len(self.trades)}: {trade['Name']} ---", self.log_tag)
                start_time1 = time.time()

                # Execute the trade and close the modal (all in one session)
                self.create_draft(trade, i + 1)
                
                log(f"Draft creation took: {(time.time() - start_time1):.2f} seconds", self.log_tag)


            log("All drafts created. Waiting for the market to open.", self.log_tag)
            
            log(f"Draft creation took: {(time.time() - start_time):.2f} seconds", self.log_tag)
            
            # BULK EXECUTION 
            self.execute_drafts()

        except Exception as e:
            log(f"FATAL ERROR during trade loop: {e}", self.log_tag, is_error=True)

        finally:
            if self.driver:
                try:
                    log("Attempting final logout.", self.log_tag)
                    time.sleep(5)
                    self.driver.find_element(By.XPATH, LOGOUT_BUTTON).click()
                except:
                    log("WARNING: Could not find or click LOGOUT button.", self.log_tag, is_error=True)
                
                time.sleep(5)
                
                log("Quitting WebDriver.", self.log_tag)
                self.driver.quit()                


