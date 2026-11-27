"""Run trusted local players and compare two paired result files."""
import argparse
import asyncio
from collections import Counter
import json
import os
from pathlib import Path
from statistics import mean
import sys
import time

from game import LEVELS, SUITES, VERSION, make_board, target_cost


async def play(player, game, timeout):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        str(player.resolve()),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        limit=4096,
    )

    async def communicate():
        while True:
            process.stdin.write((json.dumps(game.observation()) + "\n").encode())
            await process.stdin.drain()
            raw = await process.stdout.readline()
            if not raw:
                return "player_exit"
            action = raw.decode("ascii").strip()
            status = game.act(action)
            if status:
                return status

    start = time.monotonic()
    try:
        status = await asyncio.wait_for(communicate(), timeout)
    except asyncio.TimeoutError:
        status = "timeout"
    except (BrokenPipeError, ConnectionResetError):
        status = "player_exit"
    except ValueError:
        status = "invalid_action"
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.communicate()
    return status, time.monotonic() - start


def challenge(cases, suite, per_level=20):
    levels = SUITES[suite]
    groups = [[r for r in cases if r["level"] == level] for level in levels]
    if any(len(group) != per_level for group in groups):
        return f"requires {per_level} cases per level"
    min_met = (per_level + 1) // 2
    passed = all(r["status"] == "complete" for r in cases) and all(
        sum(r["target_met"] for r in group) >= min_met for group in groups
    )
    return "pass" if passed else "fail"


async def run(args):
    key = args.key_file.read_bytes() if args.key_file else b"public-practice"
    if not key:
        raise SystemExit("empty board key")
    if not args.player.is_file():
        raise SystemExit(f"player not found: {args.player}")
    levels = SUITES[args.suite]
    sem = asyncio.Semaphore(args.jobs)

    async def run_one(level, index):
        async with sem:
            game, board_id = make_board(key, level, index)
            status, elapsed = await play(args.player, game, args.seconds)
            tgt = target_cost(level, game.total)
            return {
                "level": level,
                "index": index,
                "board_id": board_id,
                "status": status,
                "steps": game.steps,
                "move_cost": game.move_spent,
                "scans": game.scans,
                "scan_cost": game.scan_spent,
                "boxes": game.square_scans,
                "sniffs": game.sniffs,
                "spoil_cost": game.spoil_spent,
                "cost": game.cost,
                "target": tgt,
                "target_met": status == "complete" and game.cost <= tgt,
                "eaten": game.total - len(game.food_map),
                "total": game.total,
                "seconds": round(elapsed, 4),
            }

    tasks = [
        run_one(level, index)
        for level in levels
        for index in range(args.per_level)
    ]
    cases = list(await asyncio.gather(*tasks))
    data = {
        "version": VERSION,
        "suite": args.suite,
        "seconds_per_game": args.seconds,
        "cases": cases,
    }
    args.out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for level in levels:
        group = [row for row in cases if row["level"] == level]
        good = [row["cost"] for row in group if row["status"] == "complete"]
        print(
            level,
            dict(Counter(row["status"] for row in group)),
            "target met",
            f"{sum(row['target_met'] for row in group)}/{len(group)}",
            "mean successful cost",
            round(mean(good), 2) if good else "n/a",
        )
    print(
        f"{len(cases)}-board {args.suite} challenge:",
        challenge(cases, args.suite),
    )


def decide_verdict(cases_a, cases_b, suite):
    levels = SUITES[suite]
    per_level = len(cases_a) // len(levels)
    comp_a = sum(r["status"] == "complete" for r in cases_a)
    comp_b = sum(r["status"] == "complete" for r in cases_b)
    met_a = sum(r["target_met"] for r in cases_a)
    met_b = sum(r["target_met"] for r in cases_b)
    by_key_a = {(r["level"], r["index"]): r for r in cases_a}
    by_key_b = {(r["level"], r["index"]): r for r in cases_b}
    both = [
        k for k in by_key_a
        if by_key_a[k]["status"] == "complete" and by_key_b[k]["status"] == "complete"
    ]
    diff = mean(by_key_b[k]["cost"] - by_key_a[k]["cost"] for k in both) if both else None

    if per_level == 20:
        pass_a = challenge(cases_a, suite, 20) == "pass"
        pass_b = challenge(cases_b, suite, 20) == "pass"
        if pass_a != pass_b:
            return "B" if pass_b else "A", "challenge_pass"
        if pass_a and pass_b:
            if diff is None or diff == 0:
                return "tie", "paired_mean_cost"
            return ("B" if diff < 0 else "A"), "paired_mean_cost"

    if comp_a != comp_b:
        return ("B" if comp_b > comp_a else "A"), "complete_count"
    if comp_a == len(cases_a) and comp_b == len(cases_b):
        if diff is None or diff == 0:
            return "tie", "paired_mean_cost"
        return ("B" if diff < 0 else "A"), "paired_mean_cost"
    if met_a != met_b:
        return ("B" if met_b > met_a else "A"), "target_met_count"
    if diff is None or diff == 0:
        return "tie", "paired_mean_cost"
    return ("B" if diff < 0 else "A"), "paired_mean_cost"


def compare(left, right):
    a, b = [json.loads(path.read_text(encoding="utf-8")) for path in (left, right)]
    if (
        a["version"] != VERSION
        or b["version"] != VERSION
        or a.get("suite") != b.get("suite")
        or a["seconds_per_game"] != b["seconds_per_game"]
    ):
        raise SystemExit("version, suite, or time limits differ")
    suite = a.get("suite", "standard")

    def index(result):
        rows = result["cases"]
        indexed = {(r["level"], r["index"], r["board_id"]): r for r in rows}
        if not indexed or len(indexed) != len(rows):
            raise SystemExit("empty or duplicate cases")
        return indexed

    x, y = index(a), index(b)
    if x.keys() != y.keys():
        raise SystemExit("board sets differ")
    for level in [*SUITES[suite], "all"]:
        keys = [k for k in x if level == "all" or k[0] == level]
        if not keys:
            continue
        ax = {k for k in keys if x[k]["status"] == "complete"}
        by = {k for k in keys if y[k]["status"] == "complete"}
        both = ax & by
        diff = mean(y[k]["cost"] - x[k]["cost"] for k in both) if both else None
        targets_a = sum(x[k]["target_met"] for k in keys)
        targets_b = sum(y[k]["target_met"] for k in keys)
        print(
            f"{level}: n={len(keys)} A_complete={len(ax)} B_complete={len(by)} "
            f"A_only={len(ax - by)} B_only={len(by - ax)} paired_n={len(both)} "
            f"A_targets={targets_a} B_targets={targets_b} "
            f"mean_cost_B_minus_A={round(diff, 2) if diff is not None else 'n/a'}"
        )
    winner, criterion = decide_verdict(a["cases"], b["cases"], suite)
    print(f"verdict: {winner} (by {criterion})")


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    bench = commands.add_parser("run")
    bench.add_argument("player", type=Path)
    bench.add_argument("--out", type=Path, required=True)
    bench.add_argument("--suite", choices=tuple(SUITES), default="standard")
    bench.add_argument("--per-level", type=int, default=5)
    bench.add_argument("--seconds", type=int, default=10)
    bench.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 4))
    bench.add_argument("--key-file", type=Path)
    pair = commands.add_parser("compare")
    pair.add_argument("A", type=Path)
    pair.add_argument("B", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        if args.per_level <= 0 or args.seconds <= 0 or args.jobs <= 0:
            parser.error("case count, time limit, and jobs must be positive")
        asyncio.run(run(args))
    else:
        compare(args.A, args.B)


if __name__ == "__main__":
    main()
