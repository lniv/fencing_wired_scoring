print("en garde")
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
# buzzer : PS1240P02BT (4kHz - if using something else, may want to adjust buzzer frequency)
# banana jacks (for wired setup) : e.g. Cinch PN 108-0903-001
# 3d printed piece to hold banana jacks
# 3d printed piece(s) to hold the display upright
# 3d printed piece to holder the buzzer (mounts over the display adapter using a longer M3 screw)
# a few M3 screws - 12mm long for legs, banana jack mount, 16mm for clamping the buzzer over the latter.
# 2.2kOhm pull up resistors for the weapon lines (for wired setup).

# NOTE: currently this is foil specific ; i see no reason the flow can't be adapted to epee or sabre,
# but, 1. we may be running out of lines for the strip and 2. the (necesssary?) hardware pullups may
# make it weapon specifc, so that we'll need some additional hardware (switch, an i2c controlled matrix etc)
# to accommodate that.


from os import getenv
import time
import board
from digitalio import DigitalInOut, Pull
import pwmio

import displayio
import rgbmatrix
import framebufferio

import socketpool
import wifi

# using one of the built in buttons to allow overriding mode.
# if using anything other than a matrixportal-S3, you may want to adjust.
mode_select_pin = board.BUTTON_DOWN
mode_select_button = DigitalInOut(mode_select_pin)
mode_select_button.switch_to_input(pull=Pull.UP)

settings = {}
# we have a few keys we must have defined.
required_keys = (
    "lockout_msec",
    "min_touch_msec",
    "buzzer_time_msec",
    "delay_before_display_reset_msec",
    "update_images_when_announcing",
    "default_audio_status",
)
for key in required_keys:
    settings[key] = getenv(key)
    if settings[key] is None:
        raise KeyError(f"{key} must be defined in settings.toml")
# for now, just set variables; i'll go to using settings directly later.
lockout_msec = settings["lockout_msec"]
min_touch_msec = settings["min_touch_msec"]


print(f"Checking if we're operating wirelessly.")
wireless_minimal_keys = (
    "wifi_ssid",
    "wifi_password",
    "display_ip",
    "display_port",
    "send_touch_for_msec",
)
for name in wireless_minimal_keys:
    settings[name] = getenv(name)
    if settings[name] is None:
        print(f"{name=} not found in settings.toml ; no wireless")
if set(settings.keys()).issuperset(wireless_minimal_keys):
    print("settings.toml compatible with wireless operation.")
    # allow overriding and going to wired mode if a button is held while initializing.
    if not mode_select_button.value:
        print("HOWEVER, overiding wireless valid config by button.")
        using_wireless = False
    else:
        using_wireless = True
else:
    using_wireless = False

if using_wireless:
    touch_sent_for_msec = settings["send_touch_for_msec"]
else:
    touch_sent_for_msec = 0

print(f"{using_wireless=}")
print(f"Using {lockout_msec=}, {min_touch_msec=} and {touch_sent_for_msec=}")


# TODO: organize this better.
right_A = DigitalInOut(board.D18)
right_B = DigitalInOut(board.D8)
right_C = DigitalInOut(board.A1)
left_A = DigitalInOut(board.A4)
left_B = DigitalInOut(board.A3)
left_C = DigitalInOut(board.A2)

# buzzer for end of action ; adjust frequency to hardwawre used.
buzzer = pwmio.PWMOut(board.A0, frequency=4000, duty_cycle=0)

all_pins = (right_A, right_B, right_C, left_A, left_B, left_C)
for i, pin in enumerate(all_pins):
    print(f"Setting pin {i} to input with no pullup")
    pin.switch_to_input(pull=None)


# below seems to work, but 1. ~ 4msec worst case, barely acceptable, and
# 2. the built in pullups really are too weak - even holding a wire from the oppsite lame to the tip registers.
# i'll try addding a real 1kohm pullup.
weapon_lines = {"right": right_B, "left": left_B}
lame_lines = {"right": right_A, "left": left_A}
common_lines = {"right": right_C, "left": left_C}

# weapon lines are pulled up (and normally grounded when the tip is not depressed, for foil.)
if not using_wireless:
    # if true, we'll disable the internal pullups and need external ones.
    # for my board, these is necessary.

    HAVE_EXTERNAL_PULLUPS = getenv("HAVE_EXTERNAL_PULLUPS")
    if HAVE_EXTERNAL_PULLUPS is None:
        raise ValueError(f"Must define HAVE_EXTERNAL_PULLUPS in settings.toml")
    for side in ("right", "left"):
        if HAVE_EXTERNAL_PULLUPS > 0:
            print(f"{side} relying on external pullups on the weapon line.")
            weapon_lines[side].switch_to_input(pull=None)
        else:
            print(f"{side} no external pullups, will try to use the internal ones.")
            weapon_lines[side].switch_to_input(pull=Pull.UP)


# yes, i should split the file etc, but this is mean more as a stream of conciousness development
# than neat and maintainable - it's pretty short so far, and i want to use it with kids.


class FencingStaus:
    """
    main class handling actions.

    Args:
        update_images_when_announcing: update display upon hit or only at end of action [False]
            updating immediately is currently slow enough to be an issue, so defaulting to update
            only at the end of the action.
    """

    # image to be shown at start.
    logo_path = "/foil_icon.bmp"

    def __init__(self, update_images_when_announcing=False):
        # length of time to play buzzer for end of action.
        # (but buzzer will sound earlier; total time will be first touch to end of action, plus this.)
        self.buzzer_time_sec = settings["buzzer_time_msec"] / 1000
        # amount of time display remains lit
        self.delay_before_display_reset_sec = (
            settings["delay_before_display_reset_msec"] / 1000
        )
        print(f"Setting up, {update_images_when_announcing=}")
        self.update_images_when_announcing = update_images_when_announcing
        # the toml file is integer, for prints etc i prefer a boolean.
        self.making_noise = True if settings["default_audio_status"] else False
        self.reset_status()
        self.prep_display()
        self.display_logo()
        self.display_image_sequence()
        self.play_buzzer()

    def _update_noise_making_status(self):
        """
        we'll use the mode select button to change audio status.
        Holding it down while a tip is pressed will toggle the status.
        """
        # i only want to announce this if we're changing state, of course.
        button_pressed = not mode_select_button.value
        if button_pressed:
            self.making_noise = not self.making_noise
            print(f"{mode_select_pin} pressed; now {self.making_noise=}.")

    def prep_display(self):
        displayio.release_displays()
        self.screen_size = (64, 32)
        matrix = rgbmatrix.RGBMatrix(
            width=64,
            bit_depth=4,
            rgb_pins=[
                board.MTX_R1,
                board.MTX_G1,
                board.MTX_B1,
                board.MTX_R2,
                board.MTX_G2,
                board.MTX_B2,
            ],
            addr_pins=[
                board.MTX_ADDRA,
                board.MTX_ADDRB,
                board.MTX_ADDRC,
                board.MTX_ADDRD,
            ],
            clock_pin=board.MTX_CLK,
            latch_pin=board.MTX_LAT,
            output_enable_pin=board.MTX_OE,
        )
        self.display = framebufferio.FramebufferDisplay(matrix)
        self.root_group = displayio.Group()
        self.display.root_group = self.root_group

    def erase_display(self):
        """
        Remove all elements from our display's root group
        """
        while len(self.root_group) > 0:
            self.root_group.pop()

    def play_buzzer(self):
        if self.making_noise:
            buzzer.duty_cycle = 65535 // 2
        time.sleep(self.buzzer_time_sec)  # may want to make this configurable?
        buzzer.duty_cycle = 0

    # i could use text and shapes, but these all require libraries, which mean more prep.
    # i could fine a use for it, but minimal use only needs 4 images:
    # "FOIL" to display mode (well, not strictly necessary)
    # a red and green 32x32 rectangles
    # a white "X".
    def _add_image(self, filename, x, y):
        """
        Display a given file at a given location on our screen
        """
        t0 = time.monotonic_ns()
        bitmap = displayio.OnDiskBitmap(filename)
        dt_bitmap = (time.monotonic_ns() - t0) / 1e6
        tile = displayio.TileGrid(bitmap, pixel_shader=bitmap.pixel_shader, x=x, y=y)
        dt_tile = (time.monotonic_ns() - t0) / 1e6
        self.root_group.append(tile)
        dt_append = (time.monotonic_ns() - t0) / 1e6
        # commenting this out, as it was found to consume the majority of the time - close to 20 msec.
        # in retrospect, doh.
        # Wait for the image to load.
        # self.display.refresh(target_frames_per_second=60)
        dt_total = (time.monotonic_ns() - t0) / 1e6
        print(
            f"Adding {filename}, {dt_bitmap=:0.1f}, {dt_tile=:0.1f}, {dt_append=:0.1f}, {dt_total=:0.1f} msec"
        )

    def display_logo(self, time_sec=1.0):
        """
        flash the class logo for a given amount of time, then erase the screen
        """
        time_nsec = time_sec * 1e9
        self.erase_display()
        self._add_image(self.logo_path, 0, 0)
        tic_ns = time.monotonic_ns()
        while time.monotonic_ns() - tic_ns <= time_nsec:
            pass
        self.erase_display()

    # i create convenience methods for each of the four cases to make some of this explicit.
    # you can make it more efficient, vector or map things etc.
    def display_image_sequence(self, display_each_sec=0.5):
        """
        display the four parts, so we can see what the results will show up as.
        """
        display_each_nanosec = display_each_sec * 1e9
        for f in (
            self.display_left_valid,
            self.display_right_valid,
            self.display_right_invalid,
            self.display_left_invalid,
        ):
            self.erase_display()
            f()
            tic_ns = time.monotonic_ns()
            while time.monotonic_ns() - tic_ns <= display_each_nanosec:
                pass
        self.erase_display()

    def display_left_valid(self):
        self._add_image("/red_32x32.bmp", 0, 0)

    def display_right_valid(self):
        self._add_image("/green_32x32.bmp", int(self.screen_size[0] / 2), 0)

    def display_left_invalid(self):
        self._add_image("/white_X_32x32.bmp", 0, 0)

    def display_right_invalid(self):
        self._add_image("/white_X_32x32.bmp", int(self.screen_size[0] / 2), 0)

    def reset_status(self):
        # TODO: deepcopy to a last result, so we can reply it.
        self.status = {
            "right": {"touch_started_msec": None, "valid": False, "announced": False},
            "left": {"touch_started_msec": None, "valid": False, "announced": False},
        }
        self._update_noise_making_status()

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
        # time the action - i want to know how long this is actually taking!
        announce_start_t = time.monotonic_ns()
        if self.making_noise:
            # now i want to start the buzzer.
            buzzer.duty_cycle = 65535 // 2
        # finding out that it takes a large amount of time to display the image - about 20 msec.
        # this dominates cycle time.
        # will profile / look for other options.
        # note that at 20 msec it's still much shorter than human reaction tie, or evenn visual time.
        # it's just that we're (even more) non adherent to the rules.
        # i.e. it's enough that at least in theory both can touch "at the same time", for only 20 msec,
        # and we'd miss the second touch since it expired before we got to the main touching detection again.
        if self.update_images_when_announcing:
            # leaving intentionally very explicit
            if side == "left":
                if self.status["left"]["valid"]:
                    self.display_left_valid()
                else:
                    self.display_left_invalid()
            else:
                if self.status["right"]["valid"]:
                    self.display_right_valid()
                else:
                    self.display_right_invalid()
        announce_length_msec = (time.monotonic_ns() - announce_start_t) / 1e6
        print(
            f"Detected touch on {side}, {self.status[side]=}; took {announce_length_msec:0.3f} msec to display."
        )

    def end_action(self):
        """
        let'em know, then reset the status.
        if we want a delay before we allow the action to start, it should be here.
        """
        print(f"End of action, {self.status=}")
        if not self.update_images_when_announcing:
            # show whatever results were merited ; "announced" gets set when a touch is detected.
            # i could condense this of course, but leaving it super explicit / readable.
            if self.status["right"]["announced"]:
                if self.status["right"]["valid"]:
                    self.display_right_valid()
                else:
                    self.display_right_invalid()
            if self.status["left"]["announced"]:
                if self.status["left"]["valid"]:
                    self.display_left_valid()
                else:
                    self.display_left_invalid()
        # buzzer sounds for some extra time once action ends (lockout could be very short)
        self.play_buzzer()
        # keep the display up for some additional time.
        time.sleep(self.delay_before_display_reset_sec)
        # now reset all
        self.reset_status()
        self.erase_display()
        print(f"Since last action, {self.worst_cycle_msec=}")
        self.worst_cycle_msec = 0

    def _check_for_hit(self, now_msec: float):
        for side, other_side in (("right", "left"), ("left", "right")):
            # if we have a result for a side, don't continue checking - no need to waste time.
            if self.status[side]["announced"]:
                continue
            # first figure out if the top is depressed, and if it's on valid / on target.
            # note that this is really the only weapon (hardware) specific section.
            common_lines[side].switch_to_output(value=False)
            touch = weapon_lines[side].value
            common_lines[side].switch_to_input(pull=None)
            lame_lines[other_side].switch_to_output(value=False)
            valid_target = not weapon_lines[side].value
            lame_lines[other_side].switch_to_input(pull=None)

            if touch:
                if self.status[side]["touch_started_msec"] is None:
                    self.status[side]["touch_started_msec"] = now_msec
                    self.status[side]["valid"] = valid_target
                else:
                    # must remain touching for it to be valid.
                    self.status[side]["valid"] &= valid_target
                if now_msec - self.status[side]["touch_started_msec"] > min_touch_msec:
                    # we probably should not put the matrices in the display at this point - it slows us dowb too much.
                    self.announce(side)
            else:
                self.status[side]["touch_started_msec"] = None

    def run_forever(self):
        t0_nsec = time.monotonic_ns()
        # look for a tocuh; if it's real (i.e. passes debounce), then start a clock.
        # in the same manner, once we're touching, check validity - it has to persist for the same amount of time.
        # once we decide we have a valid touch, we use the clock to wait till the lockout time expired, at which
        # point we decide of the status (lights)
        self.worst_cycle_msec = 0
        # if we're wireless, we should only end the action after lockout + max sending delay.
        # in this case we're relying on self._check_for_hit to only mark a hit if we're within
        # the lockout time.
        if touch_sent_for_msec > 0:
            max_msec_before_closing_action = lockout_msec + touch_sent_for_msec
            print(
                f"To account for wireless delay (<= {touch_sent_for_msec} msec), {max_msec_before_closing_action=}"
            )
        else:
            print(f"Either hard wired or else {touch_sent_for_msec=} <0")
            max_msec_before_closing_action = lockout_msec

        while True:
            now_msec = time.monotonic_ns() / 1e6
            # check first if we had one or more valid touches, and the time has expired.
            if (
                self.status["right"]["announced"]
                and now_msec - self.status["right"]["touch_started_msec"]
                >= max_msec_before_closing_action
            ) or (
                self.status["left"]["announced"]
                and now_msec - self.status["left"]["touch_started_msec"]
                >= max_msec_before_closing_action
            ):
                self.end_action()
                # maybe make sure to shut off the buzzer here? i've seen an odd occasional crash that ends with no images and continuous buzzer.
                # also - add a heartbeat (console with end= "\r", and maybe a blinking dot on screen, or LED - though that may be slow.)
                continue
            self._check_for_hit(now_msec)
            # the cycle where we end the action does not get measured, which is as it should be.
            last_cycle_msec = time.monotonic_ns() / 1e6 - now_msec
            if last_cycle_msec > self.worst_cycle_msec:
                self.worst_cycle_msec = last_cycle_msec


class WirelessFencingStatus(FencingStaus):
    """
    Detect hits by receiving messages over wifi, rather than wires.
    welcome to the future, i hope.
    """

    logo_path = "/foil_wireless_icon.bmp"

    def __init__(self, update_images_when_announcing=False):
        super().__init__(update_images_when_announcing)
        print("Creating access point...")
        wifi.radio.start_ap(
            ssid=settings["wifi_ssid"], password=settings["wifi_password"]
        )
        print(f"Created access point {settings['wifi_ssid']}")
        pool = socketpool.SocketPool(wifi.radio)
        self.sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
        # setting timeout to 0.001 sec or below gets me an OSError(11)
        # a larger time gets me a timeout error (when there is no data)
        # which is more useful.
        self.sock.settimeout(
            0.0011
        )  # non blocking. (do we need to handle the exception on timeout?)
        self.sock.bind((settings["display_ip"], settings["display_port"]))

        print(
            f"Listening for UDP packets at ({settings['display_ip']}:{settings['display_port']})"
        )
        self.last_action_i = {"right": 0, "left": 0}

    def _dump_packets(self, timeout_ns):
        """
        Drop any packets in the sockets.
        Args:
            timeout_ns: loop till this (delta) time and drop any packets.
        """
        buffer = bytearray(1024)
        t0 = time.monotonic_ns()
        # hard limit to 0.1 sec
        while time.monotonic_ns() - t0 < timeout_ns:
            try:
                num_bytes = self.sock.recv_into(buffer)
                # i may comment this out once stable.
                if num_bytes > 0:
                    print(
                        f"{time.monotonic_ns()/1e9:0.2f} post action, found {num_bytes} in sockets; {buffer[:num_bytes]=}"
                    )
                else:
                    break
            except OSError as e:
                if e.args[0] != 116:  # ETIMEDOUT as expected.
                    raise (e)
                else:
                    # if we have a timeout, we're done.
                    break

    def end_action(self):
        super().end_action()
        # i want to clear any messages in the queue; spent 1/10 sec.
        self._dump_packets(timeout_ns=1e8)
        print("socket clear, reset finished\n\n")

    def _check_for_hit(self, now_msec):
        try:
            buffer = bytearray(1024)
            # todo: time this (the buffer etc creation.), if i can.
            num_bytes, remote_address = self.sock.recvfrom_into(buffer)
            if num_bytes > 0:
                data = buffer[:num_bytes].decode(
                    "utf-8"
                )  # Slice the buffer to the actual data length
                # we get e.g.
                # 3054491455081;1220707;1;right,Sent hit - slept - back in business,2,False
                t_sent, dt_ns, repeat_i, msg = data.split(";")
                side, action, action_i, valid = msg.split(",")
                if not side in ("right", "left"):
                    raise ValueError(f"{msg} must start with right or left.")
                if action == "touched":
                    action_i = int(action_i)
                    # check that we can't accidentally invalidate something when we reset the fencer boxes?
                    # FIXME : bug here (not an issue before due to long lock out time)
                    # the box is sending a next hit from its perspective, but we're still in the same cycle!
                    # if we announced, don't process!
                    if self.status[side]["announced"]:
                        # the fencer box may be alive (and send a "new" hit) before the action ends.
                        # Can be avoided by having a box side timout that's longer than the display's,
                        # but that's annoying in practice, or by communicating bidirectionally,
                        # which i'd like to avoid for now - harder to debug.
                        return
                    if self.last_action_i[side] != action_i:
                        print(
                            f"we got {side=}, {action=}, {valid=}, {repeat_i=} (at {t_sent})"
                        )
                        # first, ensure we don't handle this one again.
                        # (i could hange this, but the case where we get a later message
                        # with a better time seems far fetched.)
                        self.last_action_i[side] = action_i
                        dt_msec = float(dt_ns) * 1e-6
                        time_of_hit = now_msec - dt_msec
                        # if the other side announced, see if we're within the valid time!
                        other_side = "left" if side == "right" else "right"
                        if self.status[other_side]["touch_started_msec"] is not None:
                            other_side_time_of_hit = self.status[other_side][
                                "touch_started_msec"
                            ]
                            if time_of_hit - other_side_time_of_hit > lockout_msec:
                                print(
                                    f"{side} reported hit at {time_of_hit:0.1f} msec, but {other_side} hit at {other_side_time_of_hit:0.1f} msec, MOVE FASTER."
                                )
                                return
                        self.status[side]["touch_started_msec"] = time_of_hit
                        self.status[side]["valid"] = True if valid == "True" else False
                        self.announce(side)
                        post_announce_t_msec = time.monotonic_ns() / 1e6
                        print(
                            f"processing hit took {post_announce_t_msec - now_msec} msec"
                        )
                        # clear messages here - otherwise we assign them a later time than they should.
                        # decided on 1e4 nsec = 10 usec as a non zero time that's infinitesimal
                        self._dump_packets(1e4)
                else:
                    print(
                        f"Got {data=} from {remote_address}, not a touch, no special handling."
                    )
        except OSError as e:
            if e.args[0] != 116:  # ETIMEDOUT as expected.
                raise (e)
        except Exception as e:
            print(f"Error during reception: {e}")


# actually execute stuff...
if using_wireless:
    fencer_status = WirelessFencingStatus(
        update_images_when_announcing=settings["update_images_when_announcing"]
    )
else:
    fencer_status = FencingStaus(
        update_images_when_announcing=settings["update_images_when_announcing"]
    )
fencer_status.run_forever()
