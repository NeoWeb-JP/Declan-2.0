"""Non-blocking routine execution gate ownership regressions."""
import unittest

from routine_execution_gates import RoutineExecutionGates


class RoutineExecutionGatesTests(unittest.TestCase):
    def test_routines_have_stable_independent_locks(self):
        gates = RoutineExecutionGates()
        morning = gates.for_routine("morning")
        night = gates.for_routine("night")
        movie = gates.for_routine("movie", movie_action="start")
        bedroom = gates.for_routine("movie", movie_action="start", movie_room="bedroom")
        sexy_time = gates.sexy_time
        self.assertIs(morning, gates.for_routine("morning"))
        self.assertIs(bedroom, gates.for_routine("movie", movie_action="stop", movie_room="bedroom"))
        self.assertEqual(len({id(item) for item in (morning, night, movie, bedroom, sexy_time)}), 5)

    def test_busy_gate_does_not_block_other_routines(self):
        gates = RoutineExecutionGates()
        morning = gates.for_routine("morning")
        night = gates.for_routine("night")
        self.assertTrue(morning.acquire(blocking=False))
        try:
            self.assertFalse(gates.for_routine("morning").acquire(blocking=False))
            self.assertTrue(night.acquire(blocking=False))
            night.release()
        finally:
            morning.release()

    def test_sexy_time_is_independently_guarded(self):
        gates = RoutineExecutionGates()
        bedroom = gates.sexy_time
        self.assertTrue(bedroom.acquire(blocking=False))
        try:
            self.assertFalse(gates.sexy_time.acquire(blocking=False))
            movie = gates.for_routine("movie", movie_action="start", movie_room="bedroom")
            self.assertTrue(movie.acquire(blocking=False))
            movie.release()
        finally:
            bedroom.release()

    def test_invalid_routine_name_does_not_create_new_gate(self):
        with self.assertRaises(KeyError):
            RoutineExecutionGates().for_routine("unknown")


if __name__ == "__main__":
    unittest.main()
