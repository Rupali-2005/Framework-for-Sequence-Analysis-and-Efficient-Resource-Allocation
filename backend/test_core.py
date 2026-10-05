import unittest
from kmp import find_all
from models import Machine,Process
from scheduling import simulate
class CoreTests(unittest.TestCase):
    # Check that KMP also finds matches that overlap
    def test_kmp_overlapping_matches(self):
        self.assertEqual(
            find_all("AAAA","AA"),
            [0,1,2]
        )
    # SJF should always pick the process with less work first
    def test_sjf_uses_shortest_first(self):
        machines=[Machine(1,"VM",10)]
        procs=[
            Process(1,"long","A","A",2,50),
            Process(2,"short","A","A",1,10)
        ]
        allocs,_=simulate(machines,procs,"SJF")
        self.assertEqual(allocs[0]["process_id"],2)
if __name__=="__main__":
    unittest.main()

