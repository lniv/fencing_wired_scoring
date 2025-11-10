print("welcome to pin chechouts")
# so i don't have to look it up again (copied from https://en.wikipedia.org/wiki/Body_cord )
# The B pin is in the middle, the A pin is 1.5 cm to one side of B, and the C pin is 2 cm to the other side of B
# The A line is the "lamé" line, the B line is the "weapon" line, and the C line is the ground
# foil specific, we care about
# tip pressed : B \disconnected\ from C
# lame touching (and tip pressed!) : opposite A is connected to B (and disconnected from C - perhaps we can use that?)
# so, e.g. for right fencer:
# 1. right B is pullup, right C is ground ; check signal on B
# 2. C as VCC, left A is ground, check signal on B (if VCC : either tip is unpressed or lame is not touching, if ground, we're on target)

import time
import board
from collections import deque
from digitalio import DigitalInOut, Direction, Pull


right_A = DigitalInOut(board.D18)
right_B = DigitalInOut(board.D8)
right_C = DigitalInOut(board.A1)
left_A = DigitalInOut(board.A4)
left_B = DigitalInOut(board.A3)
left_C = DigitalInOut(board.A2)

all_pins = (right_A, right_B, right_C, left_A, left_B, left_C)
for i, pin in enumerate(all_pins):
    print(i)
    pin.switch_to_input(pull=None)


deltas = deque([], 1000)
last_time = time.monotonic_ns()
# while True:
#     for pin1, pin2 in zip(all_pins[1:], all_pins[:-1]):
#         pin1.switch_to_input(pull = Pull.UP)
#         pin2.switch_to_output(value=False)
#         res = pin1.value
#         delta_msec = (time.monotonic_ns() - last_time) / 1e6
#         deltas.append(delta_msec)
#         print(f"since last {delta_msec=:0.2f} msec, {res=}, {max(deltas)=:0.2f} msec")
#         last_time = time.monotonic_ns()

# this is too slow - about 10 msec worst case!!
# (and is probably wrong - i wrote it before thinking through it a bit more.)
if False:
# while True:
    last_time = time.monotonic_ns()
    for name, (pin1, pin2) in (
            ("right tip", (right_A, right_B)),
            ("left tip", (left_A, left_B)),
            ("right lame", (right_A, right_C)),
            ("left lame", (left_A, left_C)),
            ):
        print(name)
        pin1.switch_to_input(pull = Pull.UP)
        pin2.switch_to_output(value=False)
        res = pin1.value
        pin1.switch_to_input(pull = None)
        pin2.switch_to_input(pull= None)
        delta_msec = (time.monotonic_ns() - last_time) / 1e6
        deltas.append(delta_msec)
        print(f"since last {delta_msec=:0.2f} msec, {res=}, {max(deltas)=:0.2f} msec")


# below seems to work, but 1. ~ 4msec worst case, barely acceptable, and
# 2. the built in pullups really are too weak - even holding a wire from the oppsite lame to the tip registers.
# i'll try addding a real 1kohm pullup.
weapon_lines = {"right" : right_B, "left" : left_B}
lame_lines = {"right" : right_A, "left" : left_A}
common_lines = {"right" : right_C, "left" : left_C}

# weapon lines are pulled up (and normally grounded when the tip is not depressed)
for side in ("right", "left"):
    weapon_lines[side].switch_to_input(pull= Pull.UP)

status = {
    "right": {"touch": False, "valid" : False},
    "left" : {"touch" : False, "valid" : False}
    }

while True:
    last_time = time.monotonic_ns()
    # 1. right B is pullup, right C is ground ; check signal on B
    # 2. C as VCC, left A is ground, check signal on B (if VCC : either tip is unpressed or lame is not touching, if ground, we're on target - decided not to do that at the end.). NOTE: might be worth to instead of switching to floating inputs, to have a larger resistor on the lames and set to VCC? maybe faster.
    # also - drop the convenience function and set things directly?
    for side, other_side in (("right", "left"), ("left", "right")):
        common_lines[side].switch_to_output(value = False)
        status[side]["touch"] = weapon_lines[side].value
        common_lines[side].switch_to_input(pull= None)

        lame_lines[other_side].switch_to_output(value = False)
        status[side]["valid"] = not weapon_lines[side].value
        lame_lines[other_side].switch_to_input(pull= None)
        delta_msec = (time.monotonic_ns() - last_time) / 1e6
        deltas.append(delta_msec)
        print(f"since last {delta_msec=:0.2f} msec, {status=}, {max(deltas)=:0.2f} msec")
