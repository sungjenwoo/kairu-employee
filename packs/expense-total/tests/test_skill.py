import unittest

import skill


class Totals(unittest.TestCase):
    def test_it_adds(self):
        self.assertEqual(skill.run("lunch 120 and bus 30"), "The total is 150.")

    def test_no_numbers(self):
        self.assertEqual(skill.run("nothing"), "The total is 0.")