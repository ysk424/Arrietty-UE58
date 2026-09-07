import unittest

from arrietty_up.fan import (
    FanController,
    FanResponse,
    level_for_speed,
    level_for_speed_with_hysteresis,
    parse_response,
    parse_response_level,
)


class FakeSocket:
    def __init__(self):
        self.blocking = None
        self.bound = None
        self.sent = []
        self.responses = []
        self.closed = False

    def setblocking(self, value):
        self.blocking = value

    def bind(self, address):
        self.bound = address

    def sendto(self, payload, destination):
        self.sent.append((payload, destination))
        return len(payload)

    def recvfrom(self, _size):
        if not self.responses:
            raise BlockingIOError
        response = self.responses.pop(0)
        if isinstance(response, tuple):
            return response
        return response, ("192.168.4.1", 4210)

    def close(self):
        self.closed = True


class FanTests(unittest.TestCase):
    def test_speed_mapping(self):
        self.assertEqual(
            [
                level_for_speed(value)
                for value in (0, 0.5, 0.6, 10, 20, 30, 50)
            ],
            [0, 0, 1, 2, 4, 6, 6],
        )
        self.assertEqual(level_for_speed(float("nan")), 0)
        self.assertEqual(level_for_speed(float("inf")), 0)

    def test_speed_mapping_hysteresis_prevents_boundary_chatter(self):
        level = 5
        for speed in (24.9, 25.0, 25.4):
            level = level_for_speed_with_hysteresis(speed, level)
            self.assertEqual(level, 5)
        level = level_for_speed_with_hysteresis(25.5, level)
        self.assertEqual(level, 6)
        for speed in (25.4, 25.0, 24.6):
            level = level_for_speed_with_hysteresis(speed, level)
            self.assertEqual(level, 6)
        self.assertEqual(level_for_speed_with_hysteresis(24.5, level), 5)
        self.assertEqual(level_for_speed_with_hysteresis(0.0, level), 0)

    def test_response_parser(self):
        self.assertEqual(
            parse_response("OK LEVEL 2 TARGET 5"),
            FanResponse("LEVEL", 2, 5),
        )
        self.assertEqual(parse_response_level("OK LEVEL 4"), 4)
        self.assertEqual(parse_response_level("OK LEVEL 2 TARGET 5"), 2)
        self.assertEqual(parse_response_level("OK SYNC 3"), 3)
        self.assertIsNone(parse_response_level("ERR unknown"))
        self.assertIsNone(parse_response_level("OK LEVEL 7"))
        self.assertIsNone(parse_response_level("OK LEVEL 2 TARGET 7"))

    def test_nonblocking_udp_lifecycle_and_response(self):
        fake = FakeSocket()
        fan = FanController(lambda *_args: fake)
        self.assertTrue(fan.start())
        self.assertFalse(fake.blocking)
        self.assertEqual(fake.bound, ("0.0.0.0", 0))

        fan.tick(10.0, 100.0)
        self.assertEqual(fake.sent[-1][0], b"LEVEL 2")
        fake.responses.append(b"OK LEVEL 2 TARGET 2")
        fan.tick(10.0, 100.1)
        self.assertEqual(fan.reported_level, 2)
        self.assertEqual(fan.reported_target_level, 2)
        self.assertEqual(fan.status, "CONNECTED LEVEL 2")
        self.assertTrue(fan.connected)
        self.assertEqual(fan.short_status, "OK")

        fan.correct_reported_level(1, 100.2)
        self.assertEqual(fake.sent[-1][0], b"SYNC 3")
        self.assertEqual(fan.reported_level, 2)
        fake.responses.append(b"OK SYNC 3")
        fan.set_level(3, 100.3)
        self.assertEqual(fan.reported_level, 3)
        sent_before_stop = len(fake.sent)
        fan.stop()
        self.assertEqual(fake.sent[-1][0], b"LEVEL 0")
        self.assertEqual(len(fake.sent) - sent_before_stop, 3)
        self.assertTrue(fake.closed)
        self.assertEqual(fan.status, "STOPPED")
        self.assertEqual(fan.short_status, "OFF")

    def test_slow_ir_transition_is_not_flooded_and_timeout_retries(self):
        fake = FakeSocket()
        fan = FanController(lambda *_args: fake)
        fan.start()
        fan.tick(0.0, 10.0)
        self.assertEqual(len(fake.sent), 1)
        fan.tick(0.0, 11.0)
        self.assertEqual(len(fake.sent), 1)
        fan.tick(0.0, 12.0)
        self.assertEqual(len(fake.sent), 1)
        fan.tick(0.0, 22.0)
        self.assertEqual(len(fake.sent), 2)
        self.assertEqual(fan.status, "NO RESPONSE - CONNECT WI-FI Arrietty-Fan")
        self.assertFalse(fan.connected)
        self.assertEqual(fan.short_status, "NO ACK")

    def test_changed_target_is_sent_while_previous_command_is_pending(self):
        fake = FakeSocket()
        fan = FanController(lambda *_args: fake)
        fan.start()

        fan.set_level(6, 10.0)
        fan.set_level(0, 11.0)

        self.assertEqual([item[0] for item in fake.sent], [b"LEVEL 6", b"LEVEL 0"])

    def test_mismatched_level_and_untrusted_sender_are_diagnostic(self):
        fake = FakeSocket()
        fan = FanController(lambda *_args: fake)
        fan.start()
        fan.set_level(4, 10.0)
        fake.responses.extend(
            [
                (b"OK LEVEL 4", ("192.168.4.99", 4210)),
                b"OK LEVEL 2 TARGET 4",
            ]
        )

        fan.set_level(4, 10.1)

        self.assertEqual(fan.invalid_responses, 1)
        self.assertEqual(fan.packets_received, 2)
        self.assertEqual(fan.reported_level, 2)
        self.assertEqual(fan.status, "SETTING LEVEL 2 -> 4")
        self.assertEqual(fan.short_status, "SET")
        self.assertEqual(fan.response_age_seconds(11.1), 1.0)

    def test_exact_level_rejects_out_of_range_value(self):
        fake = FakeSocket()
        fan = FanController(lambda *_args: fake)
        fan.start()

        with self.assertRaises(ValueError):
            fan.set_level(7, 10.0)

    def test_response_work_is_bounded_per_game_tick(self):
        fake = FakeSocket()
        fan = FanController(lambda *_args: fake)
        fan.start()
        fan.set_level(0, 10.0)
        fake.responses.extend([b"ERR stale"] * 20)

        fan.set_level(0, 10.1)

        self.assertEqual(fan.packets_received, 8)
        self.assertEqual(len(fake.responses), 12)


if __name__ == "__main__":
    unittest.main()
