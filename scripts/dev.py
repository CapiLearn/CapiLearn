#Runner file to set up frontend and backend

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"

POSTGRES_HOST = "localhost"
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "55432"))

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8001
FRONTEND_PORT = 5173


def run_command(command: list[str], cwd: Path = PROJECT_ROOT) -> None:
    print(f"\nRunning: {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd)

    if result.returncode != 0:
        print(f"Command failed: {' '.join(command)}")
        sys.exit(result.returncode)


def check_command(command: list[str], cwd: Path = PROJECT_ROOT) -> bool:
    result = subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def wait_for_port(host: str, port: int, timeout_seconds: int = 60) -> bool:
    print(f"\nWaiting for {host}:{port}...")

    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                print(f"{host}:{port} is reachable.")
                return True
        except OSError:
            time.sleep(2)

    return False


def start_process(command: list[str], cwd: Path = PROJECT_ROOT) -> subprocess.Popen:
    print(f"\nStarting: {' '.join(command)}")

    if os.name == "nt":
        return subprocess.Popen(
            command,
            cwd=cwd,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

    return subprocess.Popen(command, cwd=cwd)


def main() -> None:
    print("Starting CapiLearn development environment...")

    print("\nChecking Docker...")
    if not check_command(["docker", "ps"]):
        print("Docker is not running. Start Docker Desktop and rerun this script.")
        sys.exit(1)

    print("Docker is running.")

    print("\nStarting Postgres container...")
    run_command(["docker", "compose", "up", "-d", "postgres"])

    if not wait_for_port(POSTGRES_HOST, POSTGRES_PORT, timeout_seconds=60):
        print(f"Postgres did not become reachable on port {POSTGRES_PORT}.")
        print("Check Docker Desktop, docker compose logs, and your .env POSTGRES_PORT.")
        sys.exit(1)

    print("\nRunning database migrations...")
    run_command(["uv", "run", "alembic", "upgrade", "head"])

    print("\nStarting backend and frontend...")

    backend_process = start_process(
        [
            "uv",
            "run",
            "uvicorn",
            "backend.main:app",
            "--host",
            BACKEND_HOST,
            "--port",
            str(BACKEND_PORT),
        ],
        cwd=PROJECT_ROOT,
    )

    frontend_process = start_process(
        ["npm", "run", "dev"],
        cwd=FRONTEND_DIR,
    )

    print("\nCapiLearn dev environment started.")
    print(f"Backend:  http://{BACKEND_HOST}:{BACKEND_PORT}")
    print(f"Docs:     http://{BACKEND_HOST}:{BACKEND_PORT}/docs")
    print(f"Frontend: http://localhost:{FRONTEND_PORT}")
    print("\nPress Ctrl+C here to stop both processes.")

    try:
        while True:
            backend_code = backend_process.poll()
            frontend_code = frontend_process.poll()

            if backend_code is not None:
                print(f"\nBackend stopped with code {backend_code}.")
                break

            if frontend_code is not None:
                print(f"\nFrontend stopped with code {frontend_code}.")
                break

            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping development servers...")

    finally:
        for process in [backend_process, frontend_process]:
            if process.poll() is None:
                if os.name == "nt":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.terminate()

        print("Stopped.")


if __name__ == "__main__":
    main()