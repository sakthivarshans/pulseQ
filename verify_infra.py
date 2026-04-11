import socket
import sys
import time
import os

# Set terminal colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

SERVICES = [
    ("PostgreSQL", "localhost", 5432, "Required for configuration and user data"),
    ("Redis",      "localhost", 6379, "Required for caching and real-time events"),
    ("MongoDB",    "localhost", 27017, "Required for ML error storage and RL feedback"),
    ("ChromaDB",   "localhost", 8000, "Required for vector-based incident search"),
    ("Ollama",     "localhost", 11434, "Required for local LLM (Phi-3) processing"),
]

def check_service(name, host, port, desc):
    sys.stdout.write(f"  {CYAN}Checking {BOLD}{name:12}{RESET} ({port})... ")
    sys.stdout.flush()
    
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect((host, port))
        print(f"{GREEN}ONLINE{RESET}")
        return True
    except Exception:
        print(f"{RED}OFFLINE{RESET}")
        print(f"    {YELLOW}↳ {desc}{RESET}")
        return False
    finally:
        s.close()

def main():
    print(f"\n{BOLD}NeuralOps Infrastructure Diagnostic Tool{RESET}")
    print(f"{'='*45}")
    
    all_ok = True
    for name, host, port, desc in SERVICES:
        if not check_service(name, host, port, desc):
            all_ok = False
            
    print(f"{'='*45}")
    if all_ok:
        print(f"{GREEN}{BOLD}SUCCESS:{RESET} All infrastructure services are reachable!")
        print(f"You can now run {BOLD}python start_services.py{RESET} safely.")
    else:
        print(f"{RED}{BOLD}WARNING:{RESET} Some services are unreachable.")
        print("Please ensure you have these services running natively or via Docker.")
        print(f"Example to run only infra via Docker: {BOLD}docker-compose up postgres redis mongodb chromadb ollama -d{RESET}")
    print()

if __name__ == "__main__":
    main()
