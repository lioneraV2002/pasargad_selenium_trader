# AlgoTrader: Multi-Account Bulk Order Execution Bot for Passargad trading exchange platform

This project automates the multi-account, bulk submission of stock orders to a trading platform using **Selenium** and Python's **`multiprocessing`** for concurrent execution.

It reads trade instructions and user credentials from a single **Excel file** (`.xlsx`), where each user's trades are defined in a separate sheet. The orders are drafted sequentially, followed by a time-synchronized bulk submission.

---

## Project Structure Overview

| File/Folder | Description |
| :--- | :--- |
| `orchestrator.py` | **Main entry point.** Reads all accounts and launches a separate process (`StockTrader`) for each user. |
| `stock_trader.py` | Contains the `StockTrader` class, which handles a **single user's** login, CAPTCHA, sequential drafting, market open wait, and bulk submission. |
| `utils.py` | Helper functions for logging, WebDriver setup, CAPTCHA solving (using OCR), and reading/sorting data from the Excel files. |
| `config.py` | All static configuration, including XPath selectors, URLs, and file constants. |
| `build.bat` | Automates virtual environment setup, dependencies installation, and creation of the `algotrader.exe`. |
| `deploy.bat` | Creates a **Windows Scheduled Task** to run the bot automatically before market open. |
| `requirements.txt` | Lists Python dependencies (e.g., `selenium`, `pandas`, `easyocr`, `pyinstaller`). |
| `dist/algotrader.exe` | The final executable file, created after running `build.bat`. |

---

## Prerequisites

1.  **Python 3.8+:** Must be installed and accessible via your system's PATH.
2.  **Chrome Browser:** The bot uses the Chrome WebDriver.
3.  **Data Files:** You must create the two main configuration files (`.xlsx`) as described below.
4.  **Admin Privileges:** The `deploy.bat` file must be run **"As Administrator"** to successfully create the Windows Scheduled Task.

---

## User Guide: Setting Up and Running the Executable

The core mechanism for multi-account execution is based on matching usernames in the credentials file to sheet names in the trades file.

### Step 1: Prepare Data Files (`.xlsx`)

The bot requires two Excel files (`.xlsx`) to be placed in the **same directory** as the final executable.

#### 1. `credentials.xlsx`

This file must contain **one sheet** (e.g., Sheet1) with the following exact column headers:

| username | password |
| :--- | :--- |
| `0123456789` | `MySecurePass1` |
| `user_b` | `PassForB` |

> **Note on usernames:** Due to the need to match sheet names, ensure usernames are read as strings. The code is configured to read the `username` column as a **string** to preserve leading zeros or non-numeric formatting.

#### 2. `trades.xlsx`

This file must contain **multiple sheets**. The name of each sheet **must exactly match** a `username` from `credentials.xlsx`.

**Example: Sheet Name: `user_b`**

| Name (Stock Ticker) | Price (Limit Price) | Volume (Share Count) | Direction (Buy/Sell) |
| :--- | :--- | :--- | :--- |
| `STOCK_X` | `100` | `500` | Buy |
| `STOCK_Y` | `0` | `0` | Buy |
| `STOCK_Z` | `150` | `0` | Sell |

> **Trade Parameters (Key Logic):**
>
> * **Price = 0:** The bot will select the **Best Bid/Ask Price** (Market Order).
> * **Volume = 0:** The bot will select **Maximum Available Volume**.
> * **Sorting:** Orders where `Price=0` or `Volume=0` are prioritized for drafting, as they rely on real-time data from the modal.

### Step 2: Build the Executable (`build.bat`)

Execute the **`build.bat`** file to create the standalone application.

1.  Place `build.bat`, `orchestrator.py`, `stock_trader.py`, `utils.py`, `config.py`, and `requirements.txt` in a single folder.
2.  Double-click `build.bat`.
3.  The script will:
    * Set up a virtual environment.
    * Install necessary dependencies (including PyInstaller, Pandas, and Selenium).
    * Compile `orchestrator.py` into **`algotrader.exe`** within the **`dist`** folder.

### Step 3: Deployment and Scheduling (`deploy.bat`)

Use the `deploy.bat` script to automatically set up a Windows Scheduled Task.

1.  **Move Files:** Move the following items into your final dedicated execution folder (e.g., `C:\TraderBot\`)
    * `algotrader.exe` (from the `dist` folder)
    * `credentials.xlsx`
    * `trades.xlsx`
    * `deploy.bat`
2.  **Run Deployment:** Right-click **`deploy.bat`** and select **"Run as administrator"**.
3.  The script creates a scheduled task named **`AlgoTraderDailyRun`**.

| Task Detail | Configuration |
| :--- | :--- |
| **Task Name** | `AlgoTraderDailyRun` |
| **Execution Path** | `%~dp0algotrader.exe` (The path where you placed the file) |
| **Time** | **08:35 AM** (Daily, Saturday to Wednesday) |
| **Logon Type** | **Interactive** (Runs visibly on your desktop) |

### Step 4: Monitoring and Troubleshooting

* **Log File:** All actions, including parallel login attempts, CAPTCHA results, and trade submissions, are logged to **`bot_log.txt`** in the execution directory. Each entry is tagged with the user's name (e.g., `[USER-USERA]`).
* **Visibility is Key:** For the scheduled task to work correctly, you **must be logged into your Windows user account** at the scheduled time (08:35 AM).
* **Do not minimize or obscure the browser windows** once they open, as this can interfere with Selenium's ability to interact with the elements.
* If a single user's CAPTCHA fails three times, only that user's process will terminate; the other parallel processes will continue their workflow.

---
