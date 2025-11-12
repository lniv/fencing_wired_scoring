print("welcome to timing and pin chechouts")
"""
this doesn't get executed, but i used it during bringup to measure timings
on circuitpython 10x on a matrixportal S3
can also be used to check wiring.
"""

import time
import board
from collections import deque
from digitalio import DigitalInOut, Pull

right_A = DigitalInOut(board.D18)
right_B = DigitalInOut(board.D8)
right_C = DigitalInOut(board.A1)
left_A = DigitalInOut(board.A4)
left_B = DigitalInOut(board.A3)
left_C = DigitalInOut(board.A2)


all_pins = (right_A, right_B, right_C, left_A, left_B, left_C)
for i, pin in enumerate(all_pins):
    print(f"Setting pin {i} to input with no pullup")
    pin.switch_to_input(pull=None)

# below seems to work, but 1. ~ 4msec worst case, barely acceptable, and
# 2. the built in pullups really are too weak - even holding a wire from the oppsite lame to the tip registers.
# i'll try addding a real 1kohm pullup.
weapon_lines = {"right" : right_B, "left" : left_B}
lame_lines = {"right" : right_A, "left" : left_A}
common_lines = {"right" : right_C, "left" : left_C}

# weapon lines are pulled up (and normally grounded when the tip is not depressed, for foil.)
for side in ("right", "left"):
    weapon_lines[side].switch_to_input(pull= Pull.UP)


deltas = deque([], 1000)
last_time = time.monotonic_ns()
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
