import time
from typing import Dict, Any, List, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from datetime import datetime, time as dt_time, timedelta 



# Import utilities and configuration
from utils import log, setup_webdriver, read_credentials, read_trade_data, process_and_solve_captcha
from config import (
    TARGET_URL, CREDENTIALS_CSV, TRADES_CSV, 
    LOGIN_ID_USERNAME, LOGIN_ID_PASSWORD, CAPTCHA_IMAGE, CAPTCHA_INPUT,
    LOGIN_BUTTON_XPATH, OPEN_MODAL_BUTTON_XPATH, SEQUENTIAL_MODAL_BASE_XPATH,
    MODAL_XPATHS_RELATIVE, BULK_SELECTION_BUTTON, BULK_ORDER_AND_REMOVE,
    DRAFTS_SECTION_TAB, LOGOUT_BUTTON
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
    def __init__(self):
        self.driver: Optional[webdriver.Chrome] = None  # Re-introduced single driver
        self.trades: List[Dict[str, Any]] = []
        self.username: str = ""
        self.password: str = ""

    def initialize_data(self) -> bool:
        """Loads trade instructions and credentials."""
        self.trades = read_trade_data(TRADES_CSV)
        if not self.trades:
            log("No valid trades loaded. Initialization failed.", is_error=True)
            return False

        self.username, self.password = read_credentials(CREDENTIALS_CSV)
        if not self.username or not self.password:
            log("Credentials not loaded. Initialization failed.", is_error=True)
            return False
        
        log(f"Loaded {len(self.trades)} trades and credentials successfully.", "SYSTEM")
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
            
            # wait for the page to redirect to dashboard.
            time.sleep(10)
            
            # TEST IF LOGGED IN
            self.driver.find_element(By.XPATH, OPEN_MODAL_BUTTON_XPATH)
            
            
            return True

        except NoSuchElementException:
            log("Login failed: Dashboard elements not found after attempt. Check credentials/CAPTCHA/URL.", is_error=True)
            return False
        except Exception as e:
            log(f"An unexpected error occurred during login: {e}", is_error=True)
            return False

        
        
    def create_draft(self, trade_data: Dict[str, Any], trade_index: int):
        """Executes a single trade using the established, single driver session."""
        trade_name = f"{trade_data['Name']}-{trade_index}"
        log(f"Trade execution started.", trade_name)
        
        if not self.driver:
            log("ERROR: WebDriver not available for trade execution.", trade_name, is_error=True)
            return

        try:
            # Open the trade modal (the button must be present after login)
            self.driver.find_element(By.XPATH, OPEN_MODAL_BUTTON_XPATH).click()
            
            # Select Trade Direction (Buy/Sell)
            direction = trade_data['Direction']
            direction_xpath_key = "BUY_BUTTON" if direction == "Buy" else "SELL_BUTTON"
            self._find_modal_element(direction_xpath_key).click()
            log(f"Direction set to: {direction}", trade_name)

            # Search Stock Name and Select
            search_input = self._find_modal_element("SEARCH_INPUT")
            search_input.send_keys(trade_data['Name'])
            time.sleep(0.5) 
            search_input.send_keys(Keys.ENTER)
            log(f"Stock '{trade_data['Name']}' selected.", trade_name)

            # Set Volume
            volume = trade_data['Volume']
            if volume == 0:
                self._find_modal_element("MAX_VOLUME_CLICK").click()
                log("Volume set to MAX.", trade_name)
            else:
                volume_input = self._find_modal_element("VOLUME_INPUT")
                volume_input.clear()
                volume_input.send_keys(str(volume))
                log(f"Custom volume entered: {volume}.", trade_name)
            
            # time.sleep(0.5)            
            
            # Set Price
            price = trade_data['Price']
            if price == 0:
                self._find_modal_element("LOCK_PRICE_BUTTON").click()
                log("Price set to Best Bid/Ask.", trade_name)
            else:
                price_input = self._find_modal_element("PRICE_INPUT")
                price_input.clear()
                price_input.send_keys(str(price))
                log(f"Custom price entered: {price}.", trade_name)

            # time.sleep(0.1)            

            # Draft order
            self._find_modal_element('DRAFT_SELECTION').click()
            
            self._find_modal_element('DRAFT_BUTTON').click()
            log(f"Order **Drafted** for {direction} {trade_data['Name']}.", trade_name)
            

            
        except NoSuchElementException as e:
            log(f"ERROR: Element missing during trade execution. Error: {e}", trade_name, is_error=True)
        except Exception as e:
            log(f"An unexpected error occurred during trade execution: {e}", trade_name, is_error=True)
        finally:
            # Close Modal
            try:
                self._find_modal_element("CLOSE_MODAL_BUTTON").click()
                log("Modal closed.", trade_name)
            except:
                log("WARNING: Failed to close the modal.", trade_name, is_error=True)

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
            
            time.sleep(0.5)
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
            
        
        
    def run_workflow(self):
        """The main orchestration method for the sequential trading workflow."""
        if not self.initialize_data():
            return

        self.driver = setup_webdriver() # Initialize the single driver

        self.driver.get(TARGET_URL)
        log(f"Navigated to {TARGET_URL}.")
        
        time.sleep(5)
        
        logged_in = self.login()
        
        while not logged_in:
            logged_in = self.login()
                        
        log("Login successful: Dashboard loaded.", "SYSTEM")
            
        
        try:
            log("Starting sequential trade execution loop.", "SYSTEM")

            start_time = time.time()

            # Sequential loop replaces the ThreadPoolExecutor
            for i, trade in enumerate(self.trades):
                log(f"--- Processing Trade {i + 1}/{len(self.trades)}: {trade['Name']} ---", "SYSTEM")

                # Execute the trade and close the modal (all in one session)
                self.create_draft(trade, i + 1)

            log("All drafts created. waiting for the market to open.", "SYSTEM")
            
            print("--- %s seconds ---" % (time.time() - start_time))
            
            #  BULK EXECUTION 
            self.execute_drafts()

        except Exception as e:
            log(f"FATAL ERROR during trade loop: {e}", is_error=True)

        finally:
            if self.driver:
                try:
                    log("Attempting final logout.", "SYSTEM")
                    time.sleep(5)
                    
                    # Assuming LOGOUT_BUTTON is accessible from the dashboard
                    self.driver.find_element(By.XPATH, LOGOUT_BUTTON).click()
                except:
                    log("WARNING: Could not find or click LOGOUT button.", "SYSTEM", is_error=True)
                
                time.sleep(5)
                
                log("Quitting WebDriver.", "SYSTEM")
                self.driver.quit()
                

if __name__ == "__main__":
    trader = StockTrader()
    trader.run_workflow()

    