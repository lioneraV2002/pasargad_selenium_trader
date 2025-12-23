import os
import math
import itertools
from multiprocessing import Pool, freeze_support
from typing import List, Dict, Tuple, Any

# Import components from other files (assuming these exist)
from utils import log, read_credentials
from stock_trader import StockTrader 

# Define the maximum number of concurrent processes for both phases
MAX_PROCESSES = 8


def chunk_tasks(tasks: List[Any], num_chunks: int) -> List[List[Any]]:
    """Divides a list of tasks into approximately equal chunks."""
    if num_chunks <= 0:
        return [tasks]
    
    # Calculate approximate size of each chunk
    size = math.ceil(len(tasks) / num_chunks)
    
    # Slice the list into chunks
    return [tasks[i:i + size] for i in range(0, len(tasks), size)]


# --- Worker function for the Pool (Drafting Phase 1 - BATCHED) ---
def run_batched_draft_process(task_batch: List[Tuple[str, str, str]]) -> Dict[str, str]:
    """
    Worker that initializes one driver session and runs the draft workflow
    sequentially for an entire batch of users, reusing the driver session.
    """
    pid = os.getpid()
    results: Dict[str, str] = {}
    
    if not task_batch:
        return results

    trader = None
    try:
        # Initialize the StockTrader object for this batch process (The driver is None initially)
        trader = StockTrader()
        log(f"Phase 1: Batch DRAFT Process (PID {pid}) started for {len(task_batch)} users.", "BATCH_DRAFT")

        # Loop through each user in the batch, reusing the single driver session
        for username, password, log_tag in task_batch:
            log(f"Phase 1: Starting DRAFT for user: **{username}** (PID {pid})", log_tag)
            
            # 1. Update the trader object's fields for the new user
            trader.set_user_credentials(username, password, log_tag)
            
            # 2. Initialize/Login. The first user will set up the driver. Subsequent users will re-use it.
            if not trader.initialize_session():
                results[username] = "LOGIN_FAILURE"
                continue
            
            # 3. Create all drafts for this user
            if trader.draft_single_task():
                log(f"Phase 1: DRAFT complete for user: **{username}**", log_tag)
                results[username] = "SUCCESS"
            else:
                log(f"Phase 1: DRAFT failed for user: **{username}**", log_tag, is_error=True)
                results[username] = "FAILURE"
            
            # 4. Log out and clear user state, but KEEP the driver alive
            trader.safe_logout() 
            
    except Exception as e:
        log(f"FATAL ERROR in Phase 1 batch process (PID {pid}): {e}", "BATCH_DRAFT", is_error=True)
        for username, _, _ in task_batch:
            if username not in results:
                results[username] = "PROCESS_ERROR"
    finally:
        # 5. Quit the driver ONLY when the entire batch is complete
        if trader:
            trader.quit_driver()
            
    return results


# --- Worker function for the Pool (Execution Phase 2 - BATCHED) ---
def run_batched_execution_process(task_batch: List[Tuple[str, str, str]]) -> Dict[str, str]:
    """
    Worker that initializes one driver session and runs the execution workflow
    sequentially for an entire batch of users, reusing the driver session.
    """
    pid = os.getpid()
    results: Dict[str, str] = {}
    
    if not task_batch:
        return results

    trader = None
    try:
        trader = StockTrader()
        log(f"Phase 2: Batch EXECUTION Process (PID {pid}) started for {len(task_batch)} users.", "BATCH_EXEC")

        
        # Loop through each user in the batch
        for username, password, log_tag in task_batch:
            log(f"Phase 2: Starting EXECUTION for user: **{username}** (PID {pid})", log_tag)
            
            # 1. Update the trader object's fields for the new user
            trader.set_user_credentials(username, password, log_tag)
            
            # 2. Initialize/Login for the current user (reusing the driver)
            if not trader.initialize_session():
                results[username] = "LOGIN_FAILURE"
                continue
            # 3. Synchronization Point: All processes wait for 08:44:00 AM
            log("Phase 2: All processes synchronizing for market open.", "BATCH_EXEC")
            StockTrader.wait_until_market_open()
            log("Phase 2: Synchronization complete. Starting execution batch.", "BATCH_EXEC")
        

            # 4. Execute all drafted orders
            if trader.execute_bulk_session():
                log(f"Phase 2: EXECUTION complete for user: **{username}**", log_tag)
                results[username] = "SUCCESS"
            else:
                log(f"Phase 2: EXECUTION failed for user: **{username}**", log_tag, is_error=True)
                results[username] = "FAILURE"
            
            # 5. Log out and clear user state, but KEEP the driver alive
            trader.safe_logout() 
            
    except Exception as e:
        log(f"FATAL ERROR in Phase 2 batch process (PID {pid}): {e}", "BATCH_EXEC", is_error=True)
        for username, _, _ in task_batch:
            if username not in results:
                results[username] = "PROCESS_ERROR"
    finally:
        # 6. Quit the driver ONLY when the entire batch is complete
        if trader:
            trader.quit_driver()
            
    return results


# --- Main Orchestrator ---
def main_orchestrator():
    """
    Coordinates the two-phase trading operation using batched concurrent processes.
    """
    log(" Starting Batched Two-Phase Trading Orchestrator", "ORCHESTRATOR")
    user_credentials: List[Dict[str, str]] = read_credentials()
    
    if not user_credentials:
        log("No credentials loaded. Shutting down.", "ORCHESTRATOR", is_error=True)
        return

    # Prepare tasks list: list of tuples (username, password, log_tag)
    tasks: List[Tuple[str, str, str]] = []
    for i, creds in enumerate(user_credentials[:1]):
        username = creds.get('username', f'UnknownUser{i}')
        password = creds.get('password', '')
        log_tag = f"USER-{username}" 
        if password:
            tasks.append((username, password, log_tag))
    
    if not tasks:
        log("No valid users found to process.", "ORCHESTRATOR", is_error=True)
        return

    # Chunk the tasks into 5 batches for the 5 processes
    task_batches = chunk_tasks(tasks, MAX_PROCESSES)

    ## PHASE 1: DRAFT CREATION (Concurrent BATCHED)
    log(f"\n PHASE 1: DRAFTING ({len(tasks)} tasks in {len(task_batches)} batches)", "ORCHESTRATOR")
    log(f"Starting Pool with MAX_PROCESSES = {MAX_PROCESSES}. Each worker reuses its driver per batch.", "ORCHESTRATOR")
    
    try:
        with Pool(processes=MAX_PROCESSES) as pool:
            # map passes the list of batches to the workers
            all_draft_results = pool.map(run_batched_draft_process, task_batches)
            
    except Exception as e:
        log(f"FATAL ERROR during DRAFTING Pool: {e}", "ORCHESTRATOR", is_error=True)
        return

    # Flatten and summarize results
    draft_results = list(itertools.chain.from_iterable(d.items() for d in all_draft_results))
    log(f" PHASE 1: DRAFTING Complete. Total users processed: {len(draft_results)}", "ORCHESTRATOR")


    StockTrader.wait_until_market_open(target_minute=44)


    ## PHASE 2: EXECUTION (Concurrent BATCHED) 
    log(f"\n PHASE 2: EXECUTION ({len(tasks)} tasks in {len(task_batches)} batches)", "ORCHESTRATOR")
    log(f"Starting Pool with MAX_PROCESSES = {MAX_PROCESSES}. All processes synchronize on 08:44:00.", "ORCHESTRATOR")

    try:
        with Pool(processes=MAX_PROCESSES) as pool:
            # map blocks until all batched tasks are complete
            all_exec_results = pool.map(run_batched_execution_process, task_batches)
            
    except Exception as e:
        log(f"FATAL ERROR during EXECUTION Pool: {e}", "ORCHESTRATOR", is_error=True)
        return

    # Flatten and summarize results
    exec_results = list(itertools.chain.from_iterable(d.items() for d in all_exec_results))
    log(f" PHASE 2: EXECUTION Complete. Total users processed: {len(exec_results)}", "ORCHESTRATOR")
    log(" Batched Two-Phase Trading Orchestrator Shutting Down.", "ORCHESTRATOR")


if __name__ == "__main__":
    freeze_support() 
    main_orchestrator()