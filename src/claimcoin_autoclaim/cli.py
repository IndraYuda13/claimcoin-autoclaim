from __future__ import annotations

from pathlib import Path
import argparse
import json

from .account_store import AccountStore
from .logging_config import configure_logging
from .services.multi_runner import MultiRunner
from .services.scheduler import Scheduler
from .state.store import StateStore


def main() -> None:
    parser = argparse.ArgumentParser(prog="claimcoin-auto")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ["check", "login-probe", "claim-once", "withdraw-once", "links-probe", "show-state", "solver-stats", "run-loop"]:
        cmd = sub.add_parser(name)
        cmd.add_argument("--config", default="accounts.yaml")
        if name == "solver-stats":
            cmd.add_argument("--account")
        if name == "run-loop":
            cmd.add_argument("--cycles", type=int)
            cmd.add_argument("--sleep-floor", type=float, default=45.0)
            cmd.add_argument("--sleep-cap", type=float, default=900.0)
            cmd.add_argument("--settle-seconds", type=float, default=5.0)

    import_cmd = sub.add_parser("import-cookies")
    import_cmd.add_argument("--config", default="accounts.yaml")
    import_cmd.add_argument("--account", required=True)
    import_cmd.add_argument("--cookies", required=True)

    args = parser.parse_args()

    if args.command == "import-cookies":
        store = AccountStore(Path(args.config))
        app_config = store.load()
        configure_logging(app_config.runtime.log_dir)
        state_store = StateStore(app_config.runtime.state_dir / "claimcoin.sqlite3")
        cookies = json.loads(Path(args.cookies).read_text())
        state_store.save_account_state(args.account, cookies, {"imported_from": args.cookies})
        print(f"[{args.account}] ok=True imported {len(cookies)} cookies from {args.cookies}")
        return

    store = AccountStore(Path(args.config))
    app_config = store.load()
    configure_logging(app_config.runtime.log_dir)
    runner = MultiRunner(app_config)

    if args.command == "check":
        results = runner.bootstrap_all()
    elif args.command == "login-probe":
        results = runner.login_probe_all()
    elif args.command == "claim-once":
        results = runner.claim_all_once()
    elif args.command == "withdraw-once":
        results = runner.withdraw_all_once()
    elif args.command == "links-probe":
        results = runner.links_probe_all()
    elif args.command == "run-loop":
        scheduler = Scheduler(
            runner,
            interval_seconds=max(args.sleep_floor, 45.0),
            min_interval_seconds=args.sleep_floor,
            max_interval_seconds=args.sleep_cap,
            settle_seconds=args.settle_seconds,
        )

        def _print_cycle(cycle: int, cycle_results, cycle_elapsed_seconds: float) -> None:
            print(f"=== cycle {cycle} elapsed_seconds={cycle_elapsed_seconds:.2f} ===")
            for result in cycle_results:
                print(f"[{result.account}] ok={result.ok} {result.detail}")
                if result.raw:
                    print(json.dumps(result.raw, indent=2, sort_keys=True))

        scheduler.run_forever(max_cycles=args.cycles, on_cycle=_print_cycle)
        return
    elif args.command == "show-state":
        for account in app_config.accounts:
            if not account.enabled:
                continue
            snapshot = runner.state_store.load_account_state(account.email)
            print(json.dumps({"account": account.email, **snapshot}, indent=2, sort_keys=True))
        return
    else:
        summary = runner.state_store.summarize_antibot_attempts(account=getattr(args, "account", None))
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    for result in results:
        print(f"[{result.account}] ok={result.ok} {result.detail}")
        if result.raw:
            print(json.dumps(result.raw, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
