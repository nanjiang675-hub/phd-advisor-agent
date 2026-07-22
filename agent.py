from __future__ import annotations

import argparse
import os
import threading
import time
import webbrowser

from src.db import init_db
from src.exporter import export_results
from src.pipeline import run_pipeline
from src.webapp import serve


def run_scan() -> None:
    try:
        run_pipeline()
        export_results()
    except Exception as exc:
        print(f"scheduled scan failed: {exc}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Continuous PhD faculty discovery agent"
    )
    parser.add_argument(
        "command",
        choices=["init", "run", "export", "serve", "scheduler", "service"],
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one scheduled cycle and exit",
    )
    args = parser.parse_args()

    if args.command == "init":
        init_db(load_inputs=True)

    elif args.command == "run":
        run_pipeline()

    elif args.command == "export":
        export_results()

    elif args.command == "serve":
        url = f"http://127.0.0.1:{os.getenv('PORT', '8765')}/"
        if os.getenv("NO_BROWSER") != "1":
            webbrowser.open(url)
        serve()

    elif args.command == "scheduler":
        interval = int(os.getenv("SCAN_INTERVAL_HOURS", "168")) * 3600
        while True:
            run_scan()
            if args.once:
                break
            time.sleep(interval)

    else:
        def worker() -> None:
            interval = int(
                os.getenv("SCAN_INTERVAL_HOURS", "168")
            ) * 3600
            bootstrap_cycles = int(
                os.getenv("BOOTSTRAP_CYCLES", "3")
            )

            for cycle in range(bootstrap_cycles):
                print(
                    f"Starting initial scan "
                    f"{cycle + 1}/{bootstrap_cycles}",
                    flush=True,
                )
                run_scan()
                time.sleep(5)

            while True:
                time.sleep(interval)
                run_scan()

        init_db(load_inputs=True)
        threading.Thread(
            target=worker,
            name="scheduled-scanner",
            daemon=True,
        ).start()
        serve()


if __name__ == "__main__":
    main()
