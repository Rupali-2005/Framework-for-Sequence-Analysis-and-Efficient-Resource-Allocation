import unittest
from kmp import find_all, find_all_by_capacity
from models import Machine, Process
from scheduling import simulate

class CoreTests(unittest.TestCase):
    def test_kmp_overlapping_matches(self): self.assertEqual(find_all("AAAA", "AA"), [0, 1, 2])
    def test_capacity_chunks_keep_kmp_state(self): self.assertEqual(find_all_by_capacity("XXABCD", "ABC", 3), [2])
    def test_sjf_uses_shortest_first(self):
        allocations, _ = simulate([Machine(1, "VM", 10)], [Process(1,"long","A" * 50,"A",2), Process(2,"short","A" * 10,"A",1)], "SJF")
        self.assertEqual(allocations[0]["process_id"], 2)

if __name__ == "__main__": unittest.main()
