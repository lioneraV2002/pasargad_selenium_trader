import os
from multiprocessing import Process, freeze_support
from typing import List, Dict

# Import components from other files
from utils import log, read_credentials
from stock_trader import StockTrader


def run_trader_process(username: str, password: str, log_tag: str):
    """
    Function to be executed by each separate process.
    It initializes the StockTrader for a single user and runs the workflow.
    """
    try:
        log(f"Process started for user: **{username}**", log_tag)
        trader = StockTrader(username, password, log_tag)
        trader.run_workflow()
        log(f"Process completed successfully for user: **{username}**", log_tag)
    except Exception as e:
        log(f"FATAL ERROR in process for user {username}: {e}", log_tag, is_error=True)
        

def main_orchestrator():
    """
    The main function that loads credentials and launches a process for each user.
    """
    log("--- Starting Multi-Account Trading Orchestrator ---", "ORCHESTRATOR")

    # 1. Load all credentials
    user_credentials: List[Dict[str, str]] = read_credentials()
    
    if not user_credentials:
        log("No credentials loaded. Shutting down.", "ORCHESTRATOR", is_error=True)
        return

    processes: List[Process] = []
    
    # 2. Launch a separate process for each user
    for i, creds in enumerate(user_credentials):
        username = creds.get('username', f'UnknownUser{i}')
        password = creds.get('password', '')
        # Create a unique tag for the log file
        log_tag = f"USER-{username}" 
        
        if not password:
            log(f"Skipping user {username}: Password missing.", log_tag, is_error=True)
            continue
            
        process = Process(target=run_trader_process, args=(username, password, log_tag))
        processes.append(process)
        log(f"Launching process for user: **{username}**", "ORCHESTRATOR")
        process.start()

    # 3. Wait for all processes to complete
    for process in processes:
        process.join()

    log("--- All trading processes finished. Orchestrator shutting down. ---", "ORCHESTRATOR")


if __name__ == "__main__":
    # Required for multi-processing on Windows executables (e.g., PyInstaller)
    freeze_support() 
    main_orchestrator()