import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from fake_mcp import FakeMCP  # noqa: E402
import mcd_mcp  # noqa: E402

import shift_clock  # noqa: E402


class ShiftClockTest(unittest.TestCase):
    def test_night_shift_timeline(self):
        t = shift_clock.timeline("2026-10-11", "16:00", "19:00", "07:00")
        self.assertEqual([x["at"] for x in t], ["2026-10-11 16:30", "2026-10-12 01:00", "2026-10-12 07:20"])

    def test_off_meal_no_caffeine(self):
        r = shift_clock.plan(FakeMCP(), "广州市", "医院", "2026-10-11", "16:00", "19:00", "07:00")
        off = r["meals"][2]["plan"]
        self.assertEqual(off["daypart"], "早餐")
        self.assertFalse(any(w in i["name"] for i in off["items"] for w in shift_clock.CAFFEINE))

    def test_night_meal_uses_24h_store(self):
        r = shift_clock.plan(FakeMCP(), "广州市", "医院", "2026-10-11", "16:00", "19:00", "07:00")
        self.assertEqual(r["meals"][1]["plan"]["storeName"], "B店")


if __name__ == "__main__":
    unittest.main()