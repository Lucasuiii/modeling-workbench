"""Executable JSON-lines player. Deterministic full-board sweep baseline."""
import json
import sys


def _sweep_step(x, y, width, height, vdir):
    # vdir == 1 sweeps top->bottom; vdir == -1 sweeps bottom->top.
    row_dir = 1 if (y % 2 == 0) else -1
    if vdir == -1:
        row_dir = -row_dir if (height % 2 == 1) else row_dir
    if 0 <= x + row_dir < width:
        return "R" if row_dir == 1 else "L"
    if 0 <= y + vdir < height:
        return "D" if vdir == 1 else "U"
    return None


class BaselinePlayer:
    def __init__(self):
        self.vdir = 1
        self.corner_wait = False

    def choose(self, obs):
        x, y = obs["body"][0]
        width, height = obs["size"]
        if obs["level"] != "marsh":
            dx = 1 if y % 2 == 0 else -1
            if 0 <= x + dx < width:
                return "R" if dx == 1 else "L"
            return "D" if y + 1 < height else "STOP"

        last = obs.get("last_scan")
        if last and last.get("axis") == "SNIFF":
            if last.get("dist") is None:
                return "STOP"
            self.vdir = -self.vdir
            self.corner_wait = False

        if self.corner_wait:
            if obs["large_wait"] == 0:
                return "SNIFF"
            return "L" if x == width - 1 else "R"

        step = _sweep_step(x, y, width, height, self.vdir)
        if step is not None:
            return step

        if obs["large_wait"] == 0:
            return "SNIFF"
        self.corner_wait = True
        return "L" if x == width - 1 else "R"


_DEFAULT = BaselinePlayer()


def choose(obs):
    if obs["steps"] == 0 and obs["cost"] == 0:
        _DEFAULT.vdir = 1
        _DEFAULT.corner_wait = False
    return _DEFAULT.choose(obs)


if __name__ == "__main__":
    player = BaselinePlayer()
    for line in sys.stdin:
        print(player.choose(json.loads(line)), flush=True)
