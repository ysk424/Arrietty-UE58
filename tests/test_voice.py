import unittest
from unittest.mock import patch

from arrietty_up.voice import VoiceBridge


class FakeSocket:
    def __init__(self, *_args):
        self.sent = []
        self.responses = []
        self.closed = False

    def setblocking(self, _blocking):
        pass

    def sendto(self, payload, destination):
        self.sent.append((payload, destination))
        return len(payload)

    def recv(self, _size):
        if self.responses:
            return self.responses.pop(0)
        raise BlockingIOError

    def close(self):
        self.closed = True


class VoiceBridgeTests(unittest.TestCase):
    @patch("arrietty_up.voice.socket.socket", FakeSocket)
    def test_ptt_edges_and_status(self):
        bridge = VoiceBridge()
        self.assertTrue(bridge.set_ptt_held(True))
        self.assertTrue(bridge.set_ptt_held(False))
        self.assertEqual(
            [item[0] for item in bridge._socket.sent],
            [b"ARRIETTY_VOICE/1 PTT_DOWN", b"ARRIETTY_VOICE/1 PTT_UP"],
        )
        bridge._socket.responses.append(
            b"ARRIETTY_VOICE/1 STATUS TRANSCRIBING audio"
        )
        self.assertEqual(bridge.poll(), ("TRANSCRIBING", "audio"))
        self.assertFalse(bridge.ack_pending)
        bridge.close()
        self.assertIsNone(bridge._socket)

    @patch("arrietty_up.voice.socket.socket", FakeSocket)
    def test_missing_ack_is_reported(self):
        bridge = VoiceBridge()
        self.assertTrue(bridge.set_ptt_held(True))
        result = bridge.poll(bridge.ack_deadline_seconds)
        self.assertEqual(
            result,
            (
                "PTT BRIDGE NO RESPONSE",
                "Voice bridge did not acknowledge the PTT request",
            ),
        )


if __name__ == "__main__":
    unittest.main()
