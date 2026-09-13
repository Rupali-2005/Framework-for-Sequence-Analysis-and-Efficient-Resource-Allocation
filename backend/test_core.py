import unittest
from kmp import find_all
from models import Machine, Process
from scheduling import simulate

class CoreTests(unittest.TestCase):
    def test_kmp_overlapping_matches(self): self.assertEqual(find_all("AAAA", "AA"), [0, 1, 2])
    def test_sjf_uses_shortest_first(self):
        allocations, _ = simulate([Machine(1, "VM", 10)], [Process(1,"long","A","A",2,50), Process(2,"short","A","A",1,10)], "SJF")
        self.assertEqual(allocations[0]["process_id"], 2)

if __name__ == "__main__": unittest.main()
