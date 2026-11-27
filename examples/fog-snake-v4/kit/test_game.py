import itertools
import unittest

from baseline import choose
from game import (
    CELLAR_WINDOWS,
    GROVES,
    LEVELS,
    SUITES,
    WHIFF_RADIUS,
    Game,
    footprint,
    make_board,
    target_cost,
)
from judge import challenge, decide_verdict


class FogSnakeV4Tests(unittest.TestCase):
    def test_visibility_growth_and_premature_stop(self):
        game = Game(4, 3, 1, {(1, 0), (3, 2)}, spoil_divisor=0)
        self.assertEqual(game.observation()["food"], [[1, 0]])
        self.assertIsNone(game.act("R"))
        self.assertEqual(list(game.body), [(1, 0), (0, 0)])
        self.assertEqual(game.observation()["eaten"], 1)
        self.assertEqual(game.act("STOP"), "early_stop")

    def test_spoilage_only_on_eat_and_no_hidden_leak(self):
        # Empty cell move never adds spoil_cost; eating adds steps // spoil_divisor.
        game = Game(5, 3, 1, {(3, 0), (4, 0)}, level="orchard", spoil_divisor=2)
        self.assertIsNone(game.act("R"))  # steps=1, empty
        self.assertEqual((game.steps, game.spoil_spent, game.cost), (1, 0, 1))
        self.assertIsNone(game.act("R"))  # steps=2, empty
        self.assertEqual((game.steps, game.spoil_spent, game.cost), (2, 0, 2))
        self.assertIsNone(game.act("R"))  # steps=3, eats (3,0) -> +3//2 = +1
        self.assertEqual((game.steps, game.spoil_spent, game.cost), (3, 1, 4))
        self.assertIsNone(game.act("R"))  # steps=4, eats (4,0) -> +4//2 = +2
        self.assertEqual((game.steps, game.spoil_spent, game.cost), (4, 3, 7))

    def test_query_reports_remaining_food_and_costs_without_moving(self):
        game = Game(4, 3, 1, {(3, 0), (3, 2)}, level="garden")
        initial = list(game.body)
        self.assertIsNone(game.act("COL 3"))
        self.assertEqual(game.observation()["last_scan"], {"axis": "COL", "index": 3, "count": 2})
        self.assertIsNone(game.act("ROW 1"))
        self.assertEqual(game.observation()["last_scan"]["count"], 0)
        self.assertEqual((list(game.body), game.steps, game.cost), (initial, 0, 2 * game.scan_price))
        for _ in range(3):
            self.assertIsNone(game.act("R"))
        self.assertIsNone(game.observation()["last_scan"])
        self.assertIsNone(game.act("COL 3"))
        self.assertEqual(game.observation()["last_scan"]["count"], 1)

    def test_query_limit_and_malformed_actions(self):
        game = Game(4, 4, 1, set(), level="garden")
        game.limit = game.scan_price
        for action in ("ROW -1", "COL 4", "ROW 0 1", "ROW ²", "SCAN 3", "SNIFF"):
            self.assertEqual(game.act(action), "invalid_action")
        self.assertIsNone(game.act("ROW 0"))
        self.assertEqual(game.act("COL 0"), "step_limit")
        self.assertEqual(game.act("D"), "step_limit")
        self.assertEqual(game.act("STOP"), "complete")
        self.assertEqual(game.scans, 1)

    def test_orchard_boxes_and_cooldown(self):
        g = Game(20, 16, 1, {(1, 1), (15, 10)}, level="orchard", windows=GROVES)
        self.assertEqual([q["price"] for q in g.observation()["windows"]], [3, 3, 3, 3])
        self.assertIsNone(g.act("BOX 0"))
        self.assertEqual(g.last_scan, {"axis": "BOX", "id": 0, "count": 1})
        self.assertEqual(g.large_wait(), 4)
        self.assertEqual(g.act("BOX 3"), "invalid_action")
        for _ in range(3):
            self.assertIsNone(g.act("R"))
        self.assertEqual(g.act("BOX 3"), "invalid_action")
        self.assertIsNone(g.act("R"))
        self.assertIsNone(g.act("BOX 3"))
        self.assertEqual(g.last_scan, {"axis": "BOX", "id": 3, "count": 1})

    def test_cellar_rock_move_cost_directed_rays_and_box_penetration(self):
        g = Game(
            8,
            8,
            2,
            {(2, 0), (5, 0), (7, 0), (3, 6)},
            level="cellar",
            rocks={(1, 0), (4, 0), (3, 5), (3, 7)},
            windows=[(0, 0, 6), (0, 0, 8)],
        )
        self.assertEqual(g.observation()["rocks"], [[1, 0]])
        self.assertIn([2, 0], g.observation()["food"])  # Free sight behind a rock.
        for a in ("ROW 0", "COL 0 R", "ROW 0 T", "COL 8 B", "SNIFF"):
            self.assertEqual(g.act(a), "invalid_action")
        for action, hit, count in [
            ("ROW 0 L", [1, 0], 0),
            ("ROW 0 R", [4, 0], 2),
            ("COL 3 T", [3, 5], 0),
            ("COL 3 B", [3, 7], 0),
            ("COL 2 B", None, 1),
        ]:
            self.assertIsNone(g.act(action))
            self.assertEqual((g.last_scan["hit"], g.last_scan["count"]), (hit, count))
        self.assertEqual(g.scan_spent, 5 * 2)
        self.assertIsNone(g.act("BOX 0"))
        self.assertEqual((g.last_scan["count"], g.large_wait()), (2, 5))
        # Stepping onto rock (1,0) costs 5; normal cell (2,0) costs 1.
        before = g.move_spent
        self.assertIsNone(g.act("R"))
        self.assertEqual(g.move_spent - before, 5)
        self.assertIsNone(g.act("R"))
        self.assertEqual(g.move_spent - before, 6)

    def test_marsh_sniff_startle_pinning_and_one_time_whiff(self):
        # Static fragrant berry at (4, 0) + startled frog at (3, 1).
        g = Game(
            8,
            8,
            1,
            {(4, 0), (3, 1)},
            level="marsh",
            frogs={(3, 1)},
            fragrant={(4, 0)},
            rocks={(3, 2)},
            spoil_divisor=0,
        )
        for a in ("ROW 0", "COL 0", "BOX 0", "SNIFF 1"):
            self.assertEqual(g.act(a), "invalid_action")

        # Initial SNIFF at (0, 0): nearest is min(|4-0|+|0-0|=4, |3-0|+|1-0|=4) = 4.
        self.assertIsNone(g.act("SNIFF"))
        self.assertEqual(g.last_scan, {"axis": "SNIFF", "dist": 4})
        self.assertEqual(g.large_wait(), 8)
        self.assertEqual(g.act("SNIFF"), "invalid_action")

        # Move R to (1, 0): dist to (4,0)=3 (whiff fires once!), dist to frog (3,1)=3 (no startle yet).
        self.assertIsNone(g.act("R"))
        obs = g.observation()
        self.assertEqual(obs["rustle"], 0)
        self.assertEqual(obs["whiff"], [3])

        # Move R to (2, 0): fragrant berry whiff must NOT fire a second time;
        # frog at (3,1) is at Manhattan dist == 2 from (2,0) -> jumps!
        # Valid dist==3 neighbors of (3,1): (4,1) [open] (since (3,2) is rock and (3,0),(2,1) are dist==1).
        self.assertIsNone(g.act("R"))
        obs = g.observation()
        self.assertEqual(obs["whiff"], [])
        self.assertEqual(obs["rustle"], 1)
        self.assertIn((4, 1), g.food_map)
        self.assertEqual(g.food_map[(4, 1)].jumps, 1)

        # Pinning test: frog surrounded so all dist==3 moves are blocked -> rustle==0 and stays put.
        pinned = Game(
            4,
            4,
            1,
            {(3, 0)},
            level="marsh",
            frogs={(3, 0)},
            rocks={(3, 1)},
            spoil_divisor=0,
        )
        self.assertIsNone(pinned.act("R"))  # head at (1,0): dist to (3,0) is 2; (2,0) is dist 1, (3,1) is rock.
        self.assertEqual(pinned.observation()["rustle"], 0)
        self.assertIn((3, 0), pinned.food_map)

        # Empty marsh SNIFF returns dist=None.
        empty = Game(6, 6, 1, set(), level="marsh")
        self.assertIsNone(empty.act("SNIFF"))
        self.assertEqual(empty.last_scan, {"axis": "SNIFF", "dist": None})

    def test_generated_levels_and_invariants(self):
        for i in range(15):
            garden, _ = make_board(b"v4-test", "garden", i)
            self.assertEqual((garden.total, garden.windows, len(garden.rocks)), (6, [], 0))
            self.assertEqual(garden.act("BOX 0"), "invalid_action")

            orchard, _ = make_board(b"v4-test", "orchard", i)
            self.assertEqual(orchard.windows, list(GROVES))
            self.assertEqual(orchard.radius, 1)

            cellar, _ = make_board(b"v4-test", "cellar", i)
            self.assertEqual(cellar.windows, list(CELLAR_WINDOWS))
            self.assertTrue(cellar.rocks and cellar.food.isdisjoint(cellar.rocks))
            self.assertNotIn((0, 0), cellar.rocks)

            marsh, _ = make_board(b"v4-test", "marsh", i)
            self.assertTrue(marsh.rocks and marsh.food.isdisjoint(marsh.rocks))
            self.assertTrue(all(x + y > WHIFF_RADIUS for x, y in marsh.food))
            self.assertTrue(any(s.jumps == 2 for s in marsh.food_map.values()))
            self.assertTrue(any(s.fragrant for s in marsh.food_map.values()))

    def test_tail_and_body_collision(self):
        game = Game(3, 3, 1, {(1, 0), (1, 1), (0, 1)}, spoil_divisor=0)
        for action in ("R", "D", "L", "U"):
            self.assertIsNone(game.act(action))
        self.assertEqual(game.act("D"), "collision")

    def test_boundaries_and_limit_stop(self):
        self.assertEqual(Game(2, 2, 1, set()).act("U"), "collision")
        self.assertEqual(Game(2, 2, 1, set()).act("WAIT"), "invalid_action")
        game = Game(2, 2, 1, set())
        game.limit = 8
        for action in ["R", "L"] * 4:
            self.assertIsNone(game.act(action))
        self.assertEqual(game.act("R"), "step_limit")
        self.assertEqual(game.act("STOP"), "complete")

    def test_sweep_completes_all_levels_above_target(self):
        for level in LEVELS:
            for index in range(5):
                game, digest = make_board(b"test", level, index)
                self.assertEqual(make_board(b"test", level, index)[1], digest)
                self.assertNotEqual(make_board(b"other", level, index)[1], digest)
                status = None
                while status is None:
                    status = game.act(choose(game.observation()))
                self.assertEqual(status, "complete")
                self.assertGreater(game.cost, target_cost(level, game.total))

    def test_judge_verdict_uses_paired_cost_when_both_pass(self):
        cases_a = [
            {
                "level": "marsh",
                "index": i,
                "status": "complete",
                "cost": 310,
                "target_met": (i < 12),
            }
            for i in range(20)
        ]
        cases_b = [
            {
                "level": "marsh",
                "index": i,
                "status": "complete",
                "cost": 290,
                "target_met": (i < 10),
            }
            for i in range(20)
        ]
        self.assertEqual(challenge(cases_a, "boss", 20), "pass")
        self.assertEqual(challenge(cases_b, "boss", 20), "pass")
        self.assertEqual(decide_verdict(cases_a, cases_b, "boss"), ("B", "paired_mean_cost"))
        self.assertEqual(set(SUITES["standard"]), {"garden", "orchard", "cellar"})
        self.assertEqual(SUITES["boss"], ("marsh",))


if __name__ == "__main__":
    unittest.main()
