"""Parser for the wired ESP32 controller protocol."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ControllerSample:
    sequence: int
    joystick1_x: int
    joystick1_y: int
    joystick2_x: int
    joystick2_y: int
    button_mask: int

    @property
    def joystick1(self) -> tuple[float, float]:
        return self.joystick1_x / 32767.0, self.joystick1_y / 32767.0

    @property
    def joystick2(self) -> tuple[float, float]:
        return self.joystick2_x / 32767.0, self.joystick2_y / 32767.0

    def is_pressed(self, bit_index: int) -> bool:
        return is_pressed(self.button_mask, bit_index)


@dataclass(frozen=True, slots=True)
class ButtonTransition:
    sequence: int
    previous: int
    current: int
    pressed: int
    released: int


@dataclass(slots=True)
class ButtonEdgeLatch:
    """Track edges and retain them until the game session ends.

    The first controller sample establishes a baseline, matching the UE
    runtime.  Subsequent short presses remain observable through
    ``pressed_latch`` even after the live mask has returned to zero.
    """

    initialized: bool = False
    previous_mask: int = 0
    pressed_latch: int = 0
    released_latch: int = 0
    transition_count: int = 0
    last_sequence: int = 0

    def update(self, sample: ControllerSample) -> ButtonTransition | None:
        current = sample.button_mask
        if not self.initialized:
            self.initialized = True
            self.previous_mask = current
            self.last_sequence = sample.sequence
            return None

        previous = self.previous_mask
        changed = previous ^ current
        self.previous_mask = current
        self.last_sequence = sample.sequence
        if changed == 0:
            return None

        pressed = current & ~previous
        released = previous & ~current
        self.pressed_latch |= pressed
        self.released_latch |= released
        self.transition_count += 1
        return ButtonTransition(
            sequence=sample.sequence,
            previous=previous,
            current=current,
            pressed=pressed,
            released=released,
        )


def parse_state_line(line: str) -> ControllerSample | None:
    parts = line.strip().split(",")
    if len(parts) != 7 or parts[0] != "A1":
        return None
    try:
        values = tuple(int(part, 10) for part in parts[1:])
    except ValueError:
        return None
    sequence, j1x, j1y, j2x, j2y, button_mask = values
    if not 0 <= sequence <= 0xFFFFFFFF:
        return None
    if any(not -32767 <= value <= 32767 for value in (j1x, j1y, j2x, j2y)):
        return None
    if not 0 <= button_mask <= 0xFF:
        return None
    return ControllerSample(sequence, j1x, j1y, j2x, j2y, button_mask)


def is_pressed(button_mask: int, bit_index: int) -> bool:
    return 0 <= bit_index < 8 and bool(button_mask & (1 << bit_index))
