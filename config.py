import os
import sys
from typing import Final

#  Dynamic Path Resolution 
def get_base_path():
    """Get the absolute path to the directory containing the script or exe."""
    if getattr(sys, 'frozen', False):
        # Running as a bundled executable (e.g., via PyInstaller)
        # sys.executable is the path to the .exe
        return os.path.dirname(sys.executable)
    else:
        # Running as a .py script
        # __file__ is the path to this config.py script
        return os.path.dirname(os.path.abspath(__file__))

# APP_BASE_PATH is the root folder where algotrader.exe will live
APP_BASE_PATH: Final[str] = get_base_path()
#  End Dynamic Path 


#  Global Configuration 
TARGET_URL: Final[str] = "https://app.pasargadtrader.ir/oauth/login/"
# Place the temporary captcha file in the same folder as the exe
TEMP_IMAGE_FILE: Final[str] = os.path.join(APP_BASE_PATH, "temp_captcha.jpg")


# The .exe will look for these files in the *same directory* it is in.
CREDENTIALS_EXCEL: Final[str] = os.path.join(APP_BASE_PATH, "credentials.xlsx")
TRADES_EXCEL: Final[str] = os.path.join(APP_BASE_PATH, "trades.xlsx")


#  XPaths/IDs 
# Login Elements
LOGIN_ID_USERNAME: Final[str] = "loginName"
LOGIN_ID_PASSWORD: Final[str] = "field-password"
CAPTCHA_IMAGE: Final[str] = "/html/body/app-root/app-auth-old/div/app-auth-box/div/div/app-login-box/form/div[5]/img[2]"
CAPTCHA_INPUT: Final[str] = "/html/body/app-root/app-auth-old/div/app-auth-box/div/div/app-login-box/form/div[5]/input"
LOGIN_BUTTON_XPATH: Final[str] = "/html/body/app-root/app-auth-old/div/app-auth-box/div/div/app-login-box/form/div[6]/app-loading-button/button"
# Dashboard/Modal Trigger
OPEN_MODAL_BUTTON_XPATH: Final[str] = "/html/body/app-root/app-pages/div/app-header/div/div[2]/div[1]/div/i"
LOGOUT_BUTTON = '/html/body/app-root/app-pages/div/app-right-sidebar/nav/ul[2]/li[3]/a/i'

# Base XPath for the sequential modal (without index)
SEQUENTIAL_MODAL_BASE_XPATH: Final[str] = "/html/body/modal-container/div[2]/div"

# XPaths for elements INSIDE the trade modals, relative to the modal root
MODAL_XPATHS_RELATIVE: Final[dict[str, str]] = {
    "SEARCH_INPUT": "./app-order-modal/div[1]/div[1]/div/div/div/div/app-instrument-search/div/input",
    "BUY_BUTTON": "./app-order-modal/div[2]/div/div[2]/div/div/div[1]/span[1]/button",
    "SELL_BUTTON": "./app-order-modal/div[2]/div/div[2]/div/div/div[1]/span[2]/button",
    "MAX_VOLUME_CLICK": "./app-order-modal/div[2]/div/div[1]/div[4]/div[2]/span[2]",
    "LOCK_PRICE_BUTTON": "./app-order-modal/div[2]/div/div[1]/div[5]/div/app-stock-queue/div/div[2]",
    "CLOSE_MODAL_BUTTON": "./app-order-modal/div[1]/div[1]/i",
    "VOLUME_INPUT": "./app-order-modal/div[2]/div/div[2]/div/div/div[2]/div[1]/div/div[1]/input",
    "PRICE_INPUT": "./app-order-modal/div[2]/div/div[2]/div/div/div[2]/div[1]/div/div[2]/div/input",
    "DRAFT_SELECTION": './app-order-modal/div[2]/div/div[2]/div/div/div[4]/div/div/input',
    "DRAFT_BUTTON": './app-order-modal/div[2]/div/div[2]/div/div/div[4]/button/span'

}

BULK_SELECTION_BUTTON = '/html/body/app-root/app-pages/div/app-dashboard/div/div/div/app-dashboard-pages/div/div/div[2]/app-order-tabs/div/div/div[2]/div/app-draft-orders/p-table/div/table/thead/tr/th[2]/div/input'
BULK_ORDER_AND_REMOVE = '/html/body/app-root/app-pages/div/app-dashboard/div/div/div/app-dashboard-pages/div/div/div[2]/app-order-tabs/div/div/div[2]/div/app-draft-orders/div/button[4]'
DRAFTS_SECTION_TAB = '/html/body/app-root/app-pages/div/app-dashboard/div/div/div/app-dashboard-pages/div/div/div[2]/app-order-tabs/div/div/div[1]/ul/li[2]/a'

# XPath for the change password modal container
MODAL_XPATH = "/html/body/ngb-modal-window/div/div/app-change-password-modal"
# XPath for the close button (the 'i' element inside the button)
CLOSE_BUTTON_XPATH = "/html/body/ngb-modal-window/div/div/app-change-password-modal/div[1]/button/i"