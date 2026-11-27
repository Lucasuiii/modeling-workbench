"""Fog Snake v4.0. Coordinates start at the top left. Standard library only."""
from collections import deque
from dataclasses import dataclass
import hashlib
import hmac
import random


# width, height, sight radius, rock move cost, spoil divisor, scan price, sniff price, large cooldown
LEVELS = {
    "garden": (12, 10, 2, 1, 0, 3, None, 0),
    "orchard": (20, 16, 1, 1, 18, 4, None, 4),
    "cellar": (24, 18, 1, 5, 22, 2, None, 5),
    "marsh": (28, 20, 1, 3, 25, None, 8, 8),
}
SUITES = {
    "standard": ("garden", "orchard", "cellar"),
    "boss": ("marsh",),
    "all": ("garden", "orchard", "cellar", "marsh"),
}
MOVES = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}
VERSION = "fog-snake-v4"
BOX_PRICES = {6: 3, 7: 3, 8: 5}
WHIFF_RADIUS = 6
SQUARE_BASE = 1
SQUARE_DIVISOR = 12
LARGE_MIN_SIDE = 6
TARGET_SPEC = {
    "garden": (55, 0),
    "orchard": (60, 9),
    "cellar": (156, 10),
    "marsh": (126, 19),
}

# Public square windows (x, y, side), numbered from zero in this order.
GROVES = ((0, 0, 7), (13, 0, 7), (0, 9, 7), (13, 9, 7))
CELLAR_WINDOWS = (
    (0, 0, 6), (9, 0, 6), (18, 0, 6),
    (0, 12, 6), (9, 12, 6), (18, 12, 6),
    (3, 5, 8), (13, 5, 8),
)
WINDOWS = {
    "garden": (),
    "orchard": GROVES,
    "cellar": CELLAR_WINDOWS,
    "marsh": (),
}


@dataclass
class TargetState:
    jumps: int = 0
    fragrant: bool = False
    whiffed: bool = False


def footprint(x, y, w, h):
    return {(i, j) for i in range(x, x + w) for j in range(y, y + h)}


def target_cost(level, total):
    base, slope = TARGET_SPEC[level]
    return base + slope * total


def _place_rocks(rng, width, height, count, min_w=2, max_w=4, min_h=2, max_h=3):
    rocks = set()
    for _ in range(count):
        for _ in range(1000):
            rw = rng.randint(min_w, max_w)
            rh = rng.randint(min_h, max_h)
            rx = rng.randrange(width - rw + 1)
            ry = rng.randrange(height - rh + 1)
            deposit = footprint(rx, ry, rw, rh)
            if (0, 0) not in deposit and rocks.isdisjoint(footprint(rx - 1, ry - 1, rw + 2, rh + 2)):
                rocks.update(deposit)
                break
        else:
            raise RuntimeError("could not place rock deposit")
    return rocks


def make_board(key, level, index):
    if level not in LEVELS:
        raise ValueError(f"unknown level: {level}")
    label = f"{VERSION}/{level}/{index}".encode()
    rng = random.Random(int.from_bytes(hmac.digest(key, label, "sha256"), "big"))
    width, height, radius, rock_cost, spoil_div, scan_price, sniff_price, large_cd = LEVELS[level]
    cells = footprint(0, 0, width, height) - {(0, 0)}
    rocks = set()
    frogs = set()
    fragrant = set()

    if level == "garden":
        food = set(rng.sample(sorted(cells), 6))
    elif level == "orchard":
        chosen = rng.sample(GROVES, 2)
        food = set()
        grove_union = set()
        for g in GROVES:
            fp = footprint(g[0], g[1], g[2], g[2])
            grove_union.update(fp)
            avail_fp = sorted(fp - {(0, 0)})
            if g in chosen:
                k = rng.randint(5, 8)
                food.update(rng.sample(avail_fp, k))
            elif rng.random() < 0.20:
                food.update(rng.sample(avail_fp, 1))
        corridor = sorted(cells - grove_union)
        food.update(rng.sample(corridor, rng.randint(1, 3)))
    elif level == "cellar":
        rocks = _place_rocks(rng, width, height, rng.randint(7, 10))
        avail = cells - rocks
        chosen = rng.sample(CELLAR_WINDOWS, 2)
        food = set()
        win_union = set()
        for win in CELLAR_WINDOWS:
            fp = (footprint(win[0], win[1], win[2], win[2]) & avail) - food
            win_union.update(footprint(win[0], win[1], win[2], win[2]))
            if win in chosen:
                k = min(rng.randint(6, 9), len(fp))
                food.update(rng.sample(sorted(fp), k))
            elif fp and rng.random() < 0.15:
                food.update(rng.sample(sorted(fp), 1))
        corridor = sorted(avail - win_union)
        food.update(rng.sample(corridor, min(rng.randint(1, 2), len(corridor))))
    else:  # marsh
        rocks = _place_rocks(rng, width, height, rng.randint(8, 12))
        safe_spawn = {(x, y) for x in range(width) for y in range(height) if x + y <= WHIFF_RADIUS}
        avail = cells - rocks - safe_spawn
        count = rng.randint(10, 15)
        pts = rng.sample(sorted(avail), count)
        food = set(pts)
        n_frogs = max(4, round(0.45 * count))
        frogs = set(rng.sample(pts, n_frogs))
        n_frag = max(3, round(0.30 * count))
        fragrant = set(rng.sample(pts, n_frag))

    identity = f"{label.decode()}:{sorted(rocks)}:{sorted(food)}:{sorted(frogs)}:{sorted(fragrant)}"
    game = Game(
        width,
        height,
        radius,
        food,
        level=level,
        rocks=rocks,
        windows=WINDOWS[level],
        frogs=frogs,
        fragrant=fragrant,
        rock_move_cost=rock_cost,
        spoil_divisor=spoil_div,
        scan_price=scan_price,
        sniff_price=sniff_price,
        large_cooldown=large_cd,
    )
    return game, hashlib.sha256(identity.encode()).hexdigest()


class Game:
    def __init__(
        self,
        width,
        height,
        radius,
        food,
        *,
        level="garden",
        rocks=(),
        windows=(),
        frogs=(),
        fragrant=(),
        rock_move_cost=None,
        spoil_divisor=None,
        scan_price=None,
        sniff_price=None,
        large_cooldown=None,
    ):
        defaults = LEVELS.get(level, (width, height, radius, 1, 0, 3, None, 6))
        self.width = width
        self.height = height
        self.radius = radius
        self.level = level
        self.rocks = set(rocks)
        self.windows = list(windows)
        self.rock_move_cost = defaults[3] if rock_move_cost is None else rock_move_cost
        self.spoil_divisor = defaults[4] if spoil_divisor is None else spoil_divisor
        self.scan_price = defaults[5] if scan_price is None else scan_price
        self.sniff_price = defaults[6] if sniff_price is None else sniff_price
        self.large_cooldown = defaults[7] if large_cooldown is None else large_cooldown

        frog_set = set(frogs)
        frag_set = set(fragrant)
        self.food_map = {
            pos: TargetState(jumps=(2 if pos in frog_set else 0), fragrant=(pos in frag_set))
            for pos in food
        }
        self.total = len(self.food_map)
        self.body = deque([(0, 0)])
        self.steps = 0
        self.move_spent = 0
        self.scans = 0
        self.scan_spent = 0
        self.spoil_spent = 0
        self.square_scans = 0
        self.large_scans = 0
        self.sniffs = 0
        self.last_large_step = None
        self.last_scan = None
        self.last_rustle = 0
        self.last_whiff = []
        self.limit = 3 * width * height

    @property
    def food(self):
        return set(self.food_map.keys())

    @property
    def cost(self):
        return self.move_spent + self.scan_spent + self.spoil_spent

    @staticmethod
    def box_price(side):
        if side in BOX_PRICES:
            return BOX_PRICES[side]
        return SQUARE_BASE + (side * side + SQUARE_DIVISOR - 1) // SQUARE_DIVISOR

    def large_wait(self):
        if self.last_large_step is None or self.large_cooldown <= 0:
            return 0
        return max(0, self.large_cooldown - (self.steps - self.last_large_step))

    def observation(self):
        hx, hy = self.body[0]
        visible, stones = [], []
        for y in range(max(0, hy - self.radius), min(self.height, hy + self.radius + 1)):
            reach = self.radius - abs(y - hy)
            for x in range(max(0, hx - reach), min(self.width, hx + reach + 1)):
                if (x, y) in self.rocks:
                    stones.append([x, y])
                if (x, y) in self.food_map:
                    visible.append([x, y])
        return {
            "level": self.level,
            "size": [self.width, self.height],
            "radius": self.radius,
            "body": list(self.body),
            "food": visible,
            "rocks": stones,
            "steps": self.steps,
            "move_cost": self.move_spent,
            "scan_cost": self.scan_spent,
            "spoil_cost": self.spoil_spent,
            "cost": self.cost,
            "limit": self.limit,
            "rock_move_cost": self.rock_move_cost,
            "spoil_divisor": self.spoil_divisor,
            "scan_price": self.scan_price,
            "sniff_price": self.sniff_price,
            "windows": [
                {"id": i, "x": x, "y": y, "side": s, "price": self.box_price(s)}
                for i, (x, y, s) in enumerate(self.windows)
            ],
            "large_wait": self.large_wait(),
            "last_scan": self.last_scan,
            "rustle": self.last_rustle,
            "whiff": list(self.last_whiff),
            "eaten": self.total - len(self.food_map),
        }

    def _run_marsh_post_move(self, hx, hy):
        body_set = set(self.body)
        # Startle phase in deterministic (y, x) order.
        positions = sorted(self.food_map.keys(), key=lambda p: (p[1], p[0]))
        for fx, fy in positions:
            state = self.food_map.get((fx, fy))
            if state is None or state.jumps <= 0:
                continue
            if abs(fx - hx) + abs(fy - hy) != 2:
                continue
            best = None
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                qx, qy = fx + dx, fy + dy
                if not (0 <= qx < self.width and 0 <= qy < self.height):
                    continue
                if (qx, qy) in self.rocks or (qx, qy) in body_set or (qx, qy) in self.food_map:
                    continue
                if abs(qx - hx) + abs(qy - hy) != 3:
                    continue
                openness = sum(
                    0 <= qx + ax < self.width
                    and 0 <= qy + ay < self.height
                    and (qx + ax, qy + ay) not in self.rocks
                    and (qx + ax, qy + ay) not in body_set
                    for ax, ay in ((0, -1), (1, 0), (0, 1), (-1, 0))
                )
                cand = (openness, -qy, -qx, qx, qy)
                if best is None or cand > best:
                    best = cand
            if best is not None:
                _, _, _, qx, qy = best
                del self.food_map[(fx, fy)]
                state.jumps -= 1
                self.food_map[(qx, qy)] = state
                self.last_rustle += 1

        # One-time passive whiff phase.
        for (tx, ty), state in self.food_map.items():
            if state.fragrant and not state.whiffed:
                dist = abs(tx - hx) + abs(ty - hy)
                if dist <= WHIFF_RADIUS:
                    state.whiffed = True
                    self.last_whiff.append(dist)
        self.last_whiff.sort()

    def act(self, action):
        if action == "STOP":
            return "complete" if not self.food_map else "early_stop"

        fields = action.split()
        if action == "SNIFF":
            if self.sniff_price is None or self.large_wait():
                return "invalid_action"
            if self.cost + self.sniff_price > self.limit:
                return "step_limit"
            self.scan_spent += self.sniff_price
            self.scans += 1
            self.sniffs += 1
            self.last_large_step = self.steps
            self.last_rustle = 0
            self.last_whiff = []
            hx, hy = self.body[0]
            dist = min(
                (abs(tx - hx) + abs(ty - hy) for tx, ty in self.food_map),
                default=None,
            )
            self.last_scan = {"axis": "SNIFF", "dist": dist}
            return None

        if fields and fields[0] in ("ROW", "COL", "BOX"):
            axis = fields[0]
            if axis in ("ROW", "COL") and self.scan_price is None:
                return "invalid_action"
            directed = axis != "BOX" and self.level == "cellar"
            if len(fields) != (3 if directed else 2):
                return "invalid_action"
            token = fields[1]
            if not token.isascii() or not token.isdecimal() or len(token) > 4:
                return "invalid_action"
            index = int(token)
            if axis == "BOX":
                if index >= len(self.windows):
                    return "invalid_action"
                x, y, side = self.windows[index]
                price = self.box_price(side)
                if side >= LARGE_MIN_SIDE and self.large_wait():
                    return "invalid_action"
                result = {"axis": axis, "id": index}
                count = sum(x <= fx < x + side and y <= fy < y + side for fx, fy in self.food_map)
            else:
                is_row = axis == "ROW"
                if index >= (self.height if is_row else self.width):
                    return "invalid_action"
                length = self.width if is_row else self.height
                order = range(length)
                result = {"axis": axis, "index": index}
                if directed:
                    start = fields[2]
                    if start not in (("L", "R") if is_row else ("T", "B")):
                        return "invalid_action"
                    if start in ("R", "B"):
                        order = reversed(order)
                    result.update(start=start, hit=None)
                count = 0
                for distance in order:
                    cell = (distance, index) if is_row else (index, distance)
                    if cell in self.rocks:
                        result["hit"] = list(cell)
                        break
                    count += cell in self.food_map
                price = self.scan_price
            if self.cost + price > self.limit:
                return "step_limit"
            self.scan_spent += price
            self.scans += 1
            if axis == "BOX":
                self.square_scans += 1
                if side >= LARGE_MIN_SIDE:
                    self.large_scans += 1
                    self.last_large_step = self.steps
            self.last_rustle = 0
            self.last_whiff = []
            self.last_scan = {**result, "count": count}
            return None

        if action not in MOVES:
            return "invalid_action"
        dx, dy = MOVES[action]
        hx, hy = self.body[0]
        new = (hx + dx, hy + dy)
        step_cost = self.rock_move_cost if new in self.rocks else 1
        if self.cost + step_cost > self.limit:
            return "step_limit"

        self.last_scan = None
        self.last_rustle = 0
        self.last_whiff = []
        self.steps += 1
        self.move_spent += step_cost
        if not (0 <= new[0] < self.width and 0 <= new[1] < self.height):
            return "collision"
        grows = new in self.food_map
        if new in self.body and (grows or new != self.body[-1]):
            return "collision"
        if grows:
            del self.food_map[new]
            if self.spoil_divisor > 0:
                self.spoil_spent += self.steps // self.spoil_divisor
        else:
            self.body.pop()
        self.body.appendleft(new)
        if self.level == "marsh":
            self._run_marsh_post_move(new[0], new[1])
        return None
