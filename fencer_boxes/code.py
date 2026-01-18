"""
Code for a wireless fencer box.

need to be able to detect a switch closing, and whether we sense an AC signal (on the opponents lame), sending the results to a server.

network note: this relies on having a secrets.toml file in the root folder, which includes
netork credentials amongst other items. The included file needs to be amended.

CIRCUITPY_WIFI_SSID = "your_ssid"
CIRCUITPY_WIFI_PASSWORD = "your_ssid_passwd"

Also, we need the adafruit request library.

Since we need the settings.toml for wireless, we'll use it as a general storage.
it will have multiple sections:
1. defines network ssid / password
2. defines which side we're on - you need to edit this, either right or left
3. has common items - e.g. the frequencies used on the lames, detection thresholds, lockout times...

while i could split the settings to multiple files, i decided i preferred a single file with sections.

i'm intentionally keeping the code simple and linear - i could define classes and attributes,
but for this it makes sense to just have globals; there's really not much to it (on the fencer side)
"""

import board
from digitalio import DigitalInOut
import time
import analogbufio
import array
import math
import pwmio
import random

import wifi
import socketpool
from os import getenv


print("Reading from settings.toml")
# before we do anything else, lets see that we have a sane defintioins file.
# i could set loops etc here, but keeping names explicit makes the IDE's life easier.
settings = {}
for name in (
    "wifi_ssid",
    "wifi_password",
    "display_ip",
    "display_port",
    "fencer",
    "sampling_rate_Hz",
    "sampling_time_sec",
    "left_Hz",
    "right_Hz",
    "min_valid_power",
    "lockout_time_sec",
    "dormant_after_hit_sec",
    "message_repeat_min_sec",
    "message_repeat_max_sec",
):
    settings[name] = getenv(name)
    if settings[name] is None:
        raise RuntimeError(f"{name=} not found in settings.toml")

we_are = settings["fencer"]
if we_are == "right":
    out_freq = settings["right_Hz"]
    target_freq = settings["left_Hz"]
elif we_are == "left":
    out_freq = settings["left_Hz"]
    target_freq = settings["right_Hz"]
else:
    raise RuntimeError(
        f"{settings['fencer']=} but we must be FENCER = RIGHT or FENCER = LEFT in settings.toml"
    )

# we have a few floating point values, that due to the circuitpython toml limitations,
# must be loaded as ints. i might just change ot defining them otherwise...
for name in (
    "sampling_time_sec",
    "min_valid_power",
    "lockout_time_sec",
    "dormant_after_hit_sec",
    "message_repeat_min_sec",
    "message_repeat_max_sec",
):
    settings[name] = float(settings[name])
    if settings[name] <= 0:
        raise ValueError(f"{name} must be a positive value.")

target_address = (settings["display_ip"], settings["display_port"])

print("settings.toml looks sane; proceeding.")

print(f"{we_are=}, output at {out_freq:0.0f} Hz, looking for {target_freq:0.0f} Hz")

# hardware / pin definitions and setup

# connected to lame, through a lowpass filter, so we can do simple square wave.
# low pass will be at ~ 10kHz, so keep frequencies below that.
Lame_A_pin = board.GP13

# we have a resistor connected between the jack and each
# the pull up must be much larger than the protection resistor,
# since that's part of the line going to ground when the tip switch is closed.
# i.e. it won't "allow" it to be pulled to ground othewise.
tip_B_pull_up_pin = DigitalInOut(board.GP10)  # 100kOhm
tip_B_sense_pin = DigitalInOut(board.GP9)  # 20 kOhm
# set both to high Z to begin.
tip_B_pull_up_pin.switch_to_input(pull=None)
tip_B_sense_pin.switch_to_input(pull=None)


# set up hardare (do this before betwork setup?)
pwm_out = pwmio.PWMOut(
    Lame_A_pin, duty_cycle=2**15, frequency=out_freq, variable_frequency=False
)
print(f"Playing pwm at {out_freq} on {Lame_A_pin}")


# pretty much as taken from a random google search,
def goertzel_algorithm(samples, sample_rate, target_frequency):
    """
    Implements the Goertzel algorithm to find the power of a single frequency.

    Args:
        samples (list or np.array): The input signal (time domain samples).
        sample_rate (int): The sampling rate of the signal (Hz).
        target_frequency (float): The frequency to detect (Hz).

    Returns:
        float: The magnitude squared (power) of the target frequency.
    """
    N = len(samples)
    # Calculate the target frequency index 'k'
    k = (N * target_frequency) / sample_rate
    # Calculate the coefficient 'w_real' (cosine) and 'w_imag' (sine)
    omega = 2.0 * math.pi * k / N
    cosine = math.cos(omega)
    coefficient = 2.0 * cosine

    # Initialize the two internal states (delays)
    d1 = 0.0
    d2 = 0.0

    # Perform the main filtering loop
    for sample in samples:
        d0 = sample + coefficient * d1 - d2
        d2 = d1
        d1 = d0

    # Calculate the power (magnitude squared)
    # The result is equivalent to d1**2 + d2**2 - coefficient * d1 * d2
    power = d2**2 + d1**2 - coefficient * d1 * d2
    return power


# i could make it take e.g. a data class instance, but i'm worried about speed
# and don't want to bother profiling; for now there aren't many messages, so i think ok.
def send_msg(msg: str, t_msg: float, send_for_sec: float = 0) -> bool:
    """
    send a message to the display - which will have to parse it; simple string.
    Args:
        msg: send this to our display.
        t_msg: when it happened.
        send_for_sec: will continue sending till t_msg + this expires, randomly.
    Returns:
        True if it managed to get through, False otherwise.
    """
    t_m1 = time.monotonic()
    # TODO: refactor this so i don't have to create it each time?
    sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
    print(f"Took {(time.monotonic() - t_m1):0.5f} sec to create socket.")
    n_sent = 0
    try:
        # send once, then if we have tine, repeat.
        while n_sent < 1 or time.monotonic() - t_msg < send_for_sec:
            t_now = time.monotonic()
            sock.sendto(
                f"{t_msg:0.4f}; {t_now - t_msg:0.4f}; {msg}".encode("utf-8"),
                target_address,
            )
            t1 = time.monotonic()
            print(f"{n_sent=}, {(t_now - t_msg)=:0.4f}, {(t1 - t_msg)=:0.4f} sec")
            time.sleep(
                random.uniform(
                    settings["message_repeat_min_sec"],
                    settings["message_repeat_max_sec"],
                )
            )
            n_sent += 1
    except Exception as e:
        print(f"Error sending event: {e}")
    return n_sent > 0


############## network setup

print("Connecting to WiFi")
#  connect to your SSID
try:
    wifi.radio.connect(settings["wifi_ssid"], settings["wifi_password"])
except TypeError:
    print("Could not find WiFi info. Check your settings.toml file!")
    raise
print("Connected to WiFi")

pool = socketpool.SocketPool(wifi.radio)

#  prints MAC address to REPL
print("My MAC addr:", [hex(i) for i in wifi.radio.mac_address])
#  prints IP address to REPL
print(f"My IP address is {wifi.radio.ipv4_address}")
send_msg(f"{we_are}, Just woke up, 0, None.", time.monotonic())


############## end network stuff
# future / TODO: heartbeat to display / server, get time sync from server?
sampling_time_sec = settings["sampling_time_sec"]
sampling_rate = settings["sampling_rate_Hz"]
array_length = int(sampling_time_sec * sampling_rate)
print(f"sampling for {sampling_time_sec=}, {sampling_rate=}, N={array_length}")
mybuffer = array.array("H", [0x0000] * array_length)

t0 = time.monotonic()
ready_msg = f"{we_are}, now in business - looking for hits, 0, None"
print(t0, ready_msg)
send_msg(ready_msg, t0, 0)


def is_tip_depressed():
    """
    Returns:
        True if tip is found to be depressed/touching (circuit open).
    """
    tip_B_pull_up_pin.switch_to_output(value=True)
    touch = tip_B_sense_pin.value  # foil : circuit opens upon touch.
    tip_B_pull_up_pin.switch_to_input(pull=None)
    return touch


touch_i = 0
while True:
    t_now = time.monotonic()
    if is_tip_depressed():
        with analogbufio.BufferedIn(board.GP26, sample_rate=sampling_rate) as adcbuf:
            adcbuf.readinto(mybuffer)
        pow = goertzel_algorithm(
            mybuffer, sample_rate=sampling_rate, target_frequency=target_freq
        )
        if not is_tip_depressed():
            print("failed to find tip still pressed after checking validity, no touch.")
            continue
        touch_i += 1
        msg = f"{we_are}, touched, {touch_i}, {pow >= settings['min_valid_power']}"
        # send for the lockout perfiod; in case it wasn't received.
        send_msg(msg, t_now, settings["lockout_time_sec"])
        print(t_now, msg + f"; {pow=}")
        sleep_t = settings["dormant_after_hit_sec"] - (time.monotonic() - t_now)
        print(f"sleeping for {sleep_t:0.3f} sec")
        time.sleep(sleep_t)
        # work around for RP2350 errata E9 - the pin latches up without an external
        # pulldown smaller than 8.2K !!
        # since pulling it down to ground changes our protection, i'd rather do this.
        tip_B_sense_pin.switch_to_output(value=False)
        tip_B_sense_pin.switch_to_input(pull=None)
        post_announce_t = time.monotonic()
        msg = f"{we_are}, Sent hit - slept - back in business, {touch_i}, False"
        print(post_announce_t, msg)
        send_msg(msg, post_announce_t)
    else:
        pass
        # print(f"{touch_i=}, no touch")
