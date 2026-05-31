#!/usr/bin/env python3
import os
import time
import subprocess
import logging

# Configure logging to write to both stdout and a file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("orchestrator.log", encoding="utf-8")
    ]
)

def get_mtime(filepath):
    try:
        return os.path.getmtime(filepath)
    except OSError:
        return None

def main():
    filepath = "tasks.json"
    logging.info(f"Starting watchdog for {filepath}")
    
    # Initialize tasks.json if it doesn't exist
    if not os.path.exists(filepath):
        with open(filepath, 'w') as f:
            f.write("[]\n")
        logging.info(f"Initialized empty {filepath}")

    last_mtime = get_mtime(filepath)
    
    while True:
        try:
            time.sleep(1.0)
            current_mtime = get_mtime(filepath)
            
            if current_mtime is None:
                continue
                
            if last_mtime is None:
                last_mtime = current_mtime
                continue
                
            if current_mtime > last_mtime:
                logging.info(f"{filepath} changed! Triggering antigravity run claude_agent...")
                last_mtime = current_mtime
                
                try:
                    result = subprocess.run(
                        ["antigravity", "run", "claude_agent"],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    logging.info("Agent run finished successfully.")
                    logging.info(f"stdout: {result.stdout}")
                except subprocess.CalledProcessError as e:
                    logging.error(f"Error running antigravity: {e}")
                    logging.error(f"stdout: {e.stdout}")
                    logging.error(f"stderr: {e.stderr}")
                except FileNotFoundError:
                    logging.error("antigravity executable not found in PATH")
        except KeyboardInterrupt:
            logging.info("Stopping watchdog...")
            break
        except Exception as e:
            logging.error(f"Unexpected error in watchdog loop: {e}")

if __name__ == "__main__":
    main()
