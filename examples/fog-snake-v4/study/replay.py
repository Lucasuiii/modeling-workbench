"""Replay one published pair on the same historical boards (Python standard library)."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

STUDY = Path(__file__).resolve().parent
KIT = STUDY.parent / "kit"


def cases_digest(cases):
    rows = [{k: v for k, v in case.items() if k != "seconds"} for case in cases]
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def main():
    manifest = json.loads((STUDY / "results.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", choices=manifest["studies"])
    parser.add_argument("pair", help="See the study README for pair names.")
    parser.add_argument("--batch", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--suite", choices=("standard", "boss"), default="standard")
    args = parser.parse_args()
    data = manifest["studies"][args.study]
    if args.pair not in data["pairs"]:
        parser.error("choose a pair from " + ", ".join(data["pairs"]))
    for name, expected in manifest["kit_sha256"].items():
        if hashlib.sha256((KIT / name).read_bytes()).hexdigest() != expected:
            raise SystemExit(f"Historical kit changed: {name}")
    judge = [sys.executable, "-B", str(KIT / "judge.py")]
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        seed = folder / "board-seed"
        seed.write_bytes(bytes.fromhex(data["boards"][args.batch - 1]))
        outputs = []
        for group, entry in data["pairs"][args.pair].items():
            player_id = entry[args.suite]
            player = STUDY / "players" / f"{player_id}.py"
            if not hashlib.sha256(player.read_bytes()).hexdigest().startswith(player_id):
                raise SystemExit(f"Historical player changed: {player_id}")
            output = folder / f"{group}.json"
            print(f"Group {group}, player {player_id}", flush=True)
            subprocess.run(judge + ["run", str(player), "--suite", args.suite,
                           "--per-level", "20", "--jobs", "1", "--seconds", "10",
                           "--key-file", str(seed), "--out", str(output)], check=True)
            cases = json.loads(output.read_text(encoding="utf-8"))["cases"]
            record = data["runs"][f"{args.suite}/{player_id}"][args.batch - 1]
            if cases_digest(cases) != record["cases_sha256"]:
                raise SystemExit(f"Group {group}: replay differs from the archived cases")
            outputs.append(str(output))
        subprocess.run(judge + ["compare", *outputs], check=True)


if __name__ == "__main__":
    main()
