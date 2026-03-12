#!/usr/bin/env python3
"""
Watches ~/.openclaw/media/inbound/ for new .docx files.
Converts each to .txt using LibreOffice headless mode.
Logs conversions to ~/.openclaw/workspace/memory/docx-conversions.log
Run as a cron job or systemd service:
  @reboot sleep 30 && python3 ~/.openclaw/integrations/docx-converter/convert.py
"""
import os
import subprocess
import time
import logging
from datetime import datetime
from pathlib import Path

WATCH_DIR = Path.home() / ".openclaw/media/inbound"
LOG_PATH = Path.home() / ".openclaw/workspace/memory/docx-conversions.log"
POLL_INTERVAL_SECONDS = 15

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

def convert_docx(docx_path: Path) -> bool:
    txt_path = docx_path.with_suffix(".txt")
    if txt_path.exists():
        return False
    try:
        result = subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to", "txt:Text",
                "--outdir", str(docx_path.parent),
                str(docx_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            logging.info(f"Converted: {docx_path.name} -> {txt_path.name}")
            print(f"[OK] Converted {docx_path.name}")
            return True
        else:
            logging.error(f"Conversion failed for {docx_path.name}: {result.stderr.strip()}")
            print(f"[ERR] {docx_path.name}: {result.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        logging.error(f"Timeout converting {docx_path.name}")
        return False
    except FileNotFoundError:
        logging.error("libreoffice not found — install with: sudo apt install libreoffice")
        print("[ERR] libreoffice not installed")
        return False

def main():
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.info("docx-converter started, watching %s", WATCH_DIR)
    print(f"Watching {WATCH_DIR} every {POLL_INTERVAL_SECONDS}s...")

    while True:
        for docx_file in WATCH_DIR.glob("*.docx"):
            convert_docx(docx_file)
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
