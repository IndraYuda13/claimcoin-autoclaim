#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path

import yaml
from rich import box
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.layout import Layout
from rich.align import Align

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "accounts.yaml"
LOG = ROOT / "logs" / "run-loop-screen.log"
DB = ROOT / "state" / "claimcoin.sqlite3"


def sh(cmd: list[str], timeout: int = 5) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=timeout).strip()
    except Exception as exc:
        return f"ERR: {exc}"


def load_config() -> dict:
    try:
        return yaml.safe_load(CONFIG.read_text()) or {}
    except Exception:
        return {}


def screen_status() -> str:
    out = sh(["screen", "-ls"])
    names = []
    for line in out.splitlines():
        m = re.search(r"\d+\.([\w.-]+)\s+", line)
        if m:
            names.append(m.group(1))
    wanted = [n for n in names if n.startswith("claimcoin")]
    return ", ".join(wanted) if wanted else "no claimcoin screen"


def latest_cycles(limit: int = 10) -> list[str]:
    if not LOG.exists():
        return ["log not found"]
    lines = LOG.read_text(errors="ignore").splitlines()
    useful = []
    for line in lines[-500:]:
        if line.startswith("=== cycle") or line.startswith("["):
            useful.append(line)
    return useful[-limit:] or ["waiting for cycle output..."]


def account_table(cfg: dict) -> Table:
    table = Table(title="Accounts", box=box.ROUNDED, expand=True)
    for col in ["email", "enabled", "proxy", "withdraw", "labels"]:
        table.add_column(col)
    for acc in cfg.get("accounts", []):
        proxy = acc.get("proxy") or "-"
        proxy_label = "-"
        if proxy.startswith("http://127.0.0.1:310"):
            proxy_label = "Surfshark node-" + proxy.rsplit("310", 1)[-1]
        elif proxy:
            proxy_label = "custom"
        withdraw = "on" if (acc.get("withdraw") or {}).get("enabled") else "off"
        table.add_row(
            acc.get("email", "?"),
            "✅" if acc.get("enabled", True) else "⛔",
            proxy_label,
            withdraw,
            ", ".join(acc.get("labels") or []),
        )
    return table


def stats_panel() -> Panel:
    text = Text()
    if not DB.exists():
        text.append("state DB not found")
        return Panel(text, title="State", box=box.ROUNDED)
    try:
        con = sqlite3.connect(DB)
        cur = con.cursor()
        tables = [r[0] for r in cur.execute("select name from sqlite_master where type='table'")]
        text.append("DB: ", style="bold")
        text.append(DB.name + "\n")
        for t in tables[:8]:
            try:
                count = cur.execute(f"select count(*) from {t}").fetchone()[0]
                text.append(f"{t}: {count}\n")
            except Exception:
                pass
        con.close()
    except Exception as exc:
        text.append(f"DB error: {exc}")
    return Panel(text, title="State", box=box.ROUNDED)


def render() -> Layout:
    cfg = load_config()
    header = Text()
    header.append("ClaimCoin Control Dashboard", style="bold cyan")
    header.append(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n", style="dim")
    header.append(f"Screen: {screen_status()}\n")
    header.append(f"Cloudflare proxy: {cfg.get('cloudflare', {}).get('proxy', '-')}")

    logs = Text("\n".join(latest_cycles(16)))
    layout = Layout()
    layout.split_column(
        Layout(Panel(header, box=box.DOUBLE), size=5),
        Layout(name="main"),
        Layout(Panel(logs, title="Recent cycles", box=box.ROUNDED), size=20),
    )
    layout["main"].split_row(
        Layout(account_table(cfg), ratio=2),
        Layout(stats_panel(), ratio=1),
    )
    return layout


def main() -> None:
    console = Console()
    with Live(render(), console=console, refresh_per_second=1, screen=True) as live:
        while True:
            live.update(render())
            time.sleep(2)


if __name__ == "__main__":
    main()
