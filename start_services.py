"""
start_services.py
─────────────────
Unified startup script for all NeuralOps backend microservices.
Resilient: if one service crashes, it auto-restarts (up to 3 times).
Only exits on Ctrl+C or if a service repeatedly fails.
"""
import subprocess
import time
import sys
import os

SERVICES = [
    ("Ingestion",       "modules.ingestion.main:app",       8010),
    ("ML Engine",       "modules.ml_engine.main:app",       8020),
    ("Orchestrator",    "modules.orchestrator.main:app",    8030),
    ("RCA Engine",      "modules.rca_engine.main:app",      8040),
    ("Action Executor", "modules.action_executor.main:app", 8050),
    ("Memory Store",    "modules.memory.main:app",          8060),
    ("Chatbot",         "modules.chatbot.main:app",         8070),
    ("API Gateway",     "modules.api.main:app",             8080),
]

MAX_RESTARTS = 3


def start_service(name, module, port):
    """Launch a single uvicorn service and return the Popen object."""
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", module, "--port", str(port), "--host", "0.0.0.0"],
    )


def main():
    processes = {}   # name -> (proc, module, port, restart_count)
    print("\033[1;34m🚀 Starting NeuralOps Backend Services...\033[0m\n")
    
    # Pre-flight check: .env file
    if not os.path.exists(".env"):
        print(f"\033[1;31m[!] WARNING: .env file not found in the root directory.\033[0m")
        print(f"    Please copy .env.example to .env and configure it for local use.\n")
    else:
        # Quick verify services
        import socket
        infra_checks = [("Postgres", 5432), ("Redis", 6379), ("MongoDB", 27017)]
        missing = []
        for name, port in infra_checks:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            try:
                s.connect(("localhost", port))
            except:
                missing.append(name)
            finally:
                s.close()
        
        if missing:
            print(f"\033[1;33m[!] WARNING: The following infra services appear to be OFFLINE: {', '.join(missing)}\033[0m")
            print(f"    The services may crash or fail to connect. Run \033[1;36mpython verify_infra.py\033[0m for details.\n")

    for name, module, port in SERVICES:
        print(f"\033[1;32m[+]\033[0m Starting {name:20} on port {port}...")
        proc = start_service(name, module, port)
        processes[name] = [proc, module, port, 0]
        time.sleep(0.4)

    print(f"\n\033[1;36m✅ All {len(SERVICES)} services launched!\033[0m")
    print("\033[1;33mPress Ctrl+C to stop all services.\033[0m\n")

    try:
        while True:
            time.sleep(2)
            for name, info in list(processes.items()):
                proc, module, port, restarts = info
                if proc.poll() is not None:
                    if restarts >= MAX_RESTARTS:
                        print(f"\033[1;31m[✗] {name} failed {MAX_RESTARTS} times. Giving up.\033[0m")
                        del processes[name]
                    else:
                        print(f"\033[1;33m[↺] {name} crashed (attempt {restarts + 1}/{MAX_RESTARTS}). Restarting...\033[0m")
                        new_proc = start_service(name, module, port)
                        processes[name] = [new_proc, module, port, restarts + 1]

            if not processes:
                print("\033[1;31m[!] All services have failed. Exiting.\033[0m")
                break

    except KeyboardInterrupt:
        print("\n\033[1;33m🛑 Stopping all services...\033[0m")
        for name, info in processes.items():
            proc = info[0]
            proc.terminate()
        for name, info in processes.items():
            proc = info[0]
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("\033[1;32mDone.\033[0m")


if __name__ == "__main__":
    main()
