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

# hardware:
# display : Adafruit 64x32 matrix, specifically https://www.adafruit.com/product/2277
# controller : adafruit matrixportal S3 https://www.adafruit.com/product/5778
# buzzer : TBA
# banana jacks : e.g. Cinch PN 108-0903-001
# 3d printed piece to hold banana jacks
# 3d printed piece to hold the display upright
# 2.2kOhm pull up resistors for the weapon lines.

# NOTE: currently this is foil specific ; i see no reason the flow can't be adapted to epee or sabre,
# but, 1. we may be running out of lines for the strip and 2. the (necesssary?) hardware pullups may
# make it weapon specifc, so that we'll need some additional hardware (switch, an i2c controlled matrix etc)
# to accommodate that.

import time
import board
from collections import deque
from digitalio import DigitalInOut, Direction, Pull
import pwmio

# if set to true, we'll disable the internal pullups (which are 45kOhm, too weak really),
# and rely on external ones;
HAVE_EXTERNAL_PULLUPS = True

# set to true to just print the status to console, and do nothing else; i.e. bringup.
STATE_TESTING = False

# some rule driven constants
# reference in theory : https://static.fie.org/uploads/37/185366-technical%20rules%20ang.pdf
# but i'm finding it hard to find anything there with actual timings!
lockout_msec = 300
min_touch_msec = 10  # really debounce, not in rulebook, though i thought it was.


# TODO: organize this better.
right_A = DigitalInOut(board.D18)
right_B = DigitalInOut(board.D8)
right_C = DigitalInOut(board.A1)
left_A = DigitalInOut(board.A4)
left_B = DigitalInOut(board.A3)
left_C = DigitalInOut(board.A2)

buzzer = pwmio.PWMOut(board.A0, frequency=2500, duty_cycle=0)

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
# while True:
#     last_time = time.monotonic_ns()
#     for name, (pin1, pin2) in (
#             ("right tip", (right_A, right_B)),
#             ("left tip", (left_A, left_B)),
#             ("right lame", (right_A, right_C)),
#             ("left lame", (left_A, left_C)),
#             ):
#         print(name)
#         pin1.switch_to_input(pull = Pull.UP)
#         pin2.switch_to_output(value=False)
#         res = pin1.value
#         pin1.switch_to_input(pull = None)
#         pin2.switch_to_input(pull= None)
#         delta_msec = (time.monotonic_ns() - last_time) / 1e6
#         deltas.append(delta_msec)
#         print(f"since last {delta_msec=:0.2f} msec, {res=}, {max(deltas)=:0.2f} msec")


# below seems to work, but 1. ~ 4msec worst case, barely acceptable, and
# 2. the built in pullups really are too weak - even holding a wire from the oppsite lame to the tip registers.
# i'll try addding a real 1kohm pullup.
weapon_lines = {"right" : right_B, "left" : left_B}
lame_lines = {"right" : right_A, "left" : left_A}
common_lines = {"right" : right_C, "left" : left_C}

# weapon lines are pulled up (and normally grounded when the tip is not depressed, for foil.)
for side in ("right", "left"):
    if HAVE_EXTERNAL_PULLUPS:
        print("Relying on external pullups on the weapon lines.")
        weapon_lines[side].switch_to_input(pull= None)
    else:
        print("No external pullups, will try to use the internal ones.")
        weapon_lines[side].switch_to_input(pull= Pull.UP)


# bringup testing; should be in a util somewhere.
if STATE_TESTING:
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


# here the usual loop goes.
# yes, i should split the file etc, but this is mean more as a stream of conciousness development
# than neat and maintainable - it's pretty short so far, and i want to use it with kids.


class FencingStaus():
    def __init__(self):
        print("Start fencing")
        self.reset_status()

    def reset_status(self):
        # TODO: deepcopy to a last result, so we can reply it.
        self.status = {
            "right": {"touch_started_msec": None, "valid" : False, "announced" : False},
            "left" : {"touch_started_msec": None, "valid" : False, "announced" : False}
            }

    def announce(self, side):
        """
        light up the board when someone had a (debounced) touch.
        Args:
            side: which side did something, "right" or "left"
        """
        # don't announce more than once per action, duh.
        if self.status[side]["announced"]:
            return
        self.status[side]["announced"] = True
        print(f"Detected touch on {side}, {self.status[side]=}")

    def end_action(self):
        """
        let'em know, then reset the status.
        if we want a delay before we allow the action to start, it should be here.
        """
        # TODO: beep! we need to announce that the action is over!
        print(f"End of action, {self.status=}")
        self.reset_status()
        buzzer.duty_cycle = 65535 // 2
        time.sleep(1)  # may want to make this configurable?
        buzzer.duty_cycle = 0

    def run_forever(self):
        t0_nsec = time.monotonic_ns()
        # look for a tocuh; if it's real (i.e. passes debounce), then start a clock.
        # in the same manner, once we're touching, check validity - it has to persist for the same amount of time.
        # once we decide we have a valid touch, we use the clock to wait till the lockout time expired, at which
        # point we decide of the status (lights)
        while True:
            now_msec = (time.monotonic_ns() - t0_nsec) / 1e6
            # check first if we had one or more valid touches, and the time has expired.
            for side in ("right", "left"):
                if self.status[side]["announced"] and now_msec - self.status[side]["touch_started_msec"] > lockout_msec:
                    self.end_action()
                    continue

            for side, other_side in (("right", "left"), ("left", "right")):
                # first figure out if the top is depressed, and if it's on valid / on target.
                # note that this is really the only weapon (hardware) specific section.
                common_lines[side].switch_to_output(value = False)
                touch = weapon_lines[side].value
                common_lines[side].switch_to_input(pull= None)
                lame_lines[other_side].switch_to_output(value = False)
                valid_target = not weapon_lines[side].value
                lame_lines[other_side].switch_to_input(pull= None)

                if touch:
                    if self.status[side]["touch_started_msec"] is None:
                        self.status[side]["touch_started_msec"] = now_msec
                        self.status[side]["valid"] = valid_target
                    else:
                        # must remain touching for it to be valid.
                        self.status[side]["valid"] &= valid_target
                    if now_msec - self.status[side]["touch_started_msec"] > min_touch_msec:
                        self.announce(side)
                # i.e. once we we had a touch we leave the time unmodified till the end of the action.
                elif not self.status[side]["announced"]:
                    self.status[side]["touch_started_msec"] = None


fencer_status = FencingStaus()
fencer_status.run_forever()