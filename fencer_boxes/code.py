"""
Code for a wireless fencer box.

need to be able to detect a switch closing, and whether we sense an AC signal (on the opponents lame), sending the results to a server/display.

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


# standardize on using monotonic_ns as integer, and have times in millisec.

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
    "min_touch_msec",
    "sampling_time_msec",
    "left_Hz",
    "right_Hz",
    "min_valid_power",
    "send_touch_for_msec",
    "dormant_after_hit_msec",
    "message_repeat_min_msec",
    "message_repeat_max_msec",
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
# (i had more than one value, is swear...)
for name in ("min_valid_power",):
    settings[name] = float(settings[name])
    if settings[name] <= 0:
        raise ValueError(f"{name} must be a positive value.")

target_address = (settings["display_ip"], settings["display_port"])

# i'm using these with sleep later, and would prefer to not convert them each time.
message_repeat_min_sec = settings["message_repeat_min_msec"] / 1000
message_repeat_max_sec = settings["message_repeat_max_msec"] / 1000
dormant_after_hit_sec = settings["dormant_after_hit_msec"] / 1000
send_touch_for_ns = settings["send_touch_for_msec"] * 1e6
print(
    f"{dormant_after_hit_sec=}, {send_touch_for_ns=}, repeating every {message_repeat_min_sec:0.3f} to {message_repeat_max_sec:0.3f} sec"
)

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
def send_msg(msg: str, t_msg_ns: int, send_for_nanosec: int = 0) -> bool:
    """
    send a message to the display - which will have to parse it; simple string.
    Args:
        msg: send this to our display.
        t_msg_ns: when it happened, in nanosec.
        send_for_nanosec: will continue sending till t_msg + this expires, randomly.
    Returns:
        True if it managed to get through, False otherwise.
    """
    t_m1_ns = time.monotonic_ns()
    # TODO: refactor this so i don't have to create it each time?
    sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
    print(
        f"Took {(1e-6 * (time.monotonic_ns() - t_m1_ns)):0.1f} msec to create socket."
    )
    n_sent = 0
    try:
        # send once, then if we have tine, repeat.
        while n_sent < 1 or time.monotonic_ns() - t_msg_ns < send_for_nanosec:
            t_now_ns = time.monotonic_ns()
            n_sent += 1
            # times are in nanosec, since it's native. we usually will deal with millisec for humans.
            # dropping spaces for easier processing, at the expense of humans.
            sock.sendto(
                f"{t_msg_ns};{t_now_ns - t_msg_ns};{n_sent};{msg}".encode("utf-8"),
                target_address,
            )
            t1_ns = time.monotonic_ns()
            print(f"{n_sent=}, {(t_now_ns - t_msg_ns)=}, {(t1_ns - t_msg_ns)=} nanosec")
            time.sleep(
                random.uniform(
                    message_repeat_min_sec,
                    message_repeat_max_sec,
                )
            )
    except OSError as e:
        if e.args[0] == 118:  # EHOSTUNREACH ; try to reconnect
            print(f"Got {e=}, will try to reconnect.")
            try:
                connect_to_display()
            except Exception as e:
                print(f"Failed to reconnect due to {e}")
    except Exception as e:
        print(f"Error sending event: {e}")
    return n_sent > 0


############## network setup


def connect_to_display():
    ssid = settings["wifi_ssid"]
    passwd = settings["wifi_password"]
    print(f"Connecting to {ssid=}, {passwd=}")
    wifi.radio.connect(ssid, passwd)
    print("Connected to WiFi")


print(f"Initial connection to display AP")
while True:
    try:
        connect_to_display()
        break
    except ConnectionError as e:
        print(
            f"t = {(time.monotonic_ns() / 1e9):0.1f} sec: Failed to connect to display due to {e}, will wait 5 sec then retry."
        )
        time.sleep(5)

pool = socketpool.SocketPool(wifi.radio)

#  prints MAC address to REPL
print("My MAC addr:", [hex(i) for i in wifi.radio.mac_address])
#  prints IP address to REPL
print(f"My IP address is {wifi.radio.ipv4_address}")
send_msg(f"{we_are},Just woke up,0,None.", time.monotonic_ns())


############## end network stuff
# future / TODO: heartbeat to display / server, get time sync from server?
sampling_time_sec = settings["sampling_time_msec"] * 1e-3
sampling_rate = settings["sampling_rate_Hz"]
array_length = int(sampling_time_sec * sampling_rate)
print(f"sampling for {sampling_time_sec=}, {sampling_rate=}, N={array_length}")
print(f"vaid touch requires {settings['min_valid_power']=}")
adc_read_buffer = array.array("H", [0x0000] * array_length)

t0_ns = time.monotonic_ns()
ready_msg = f"{we_are},now in business - looking for hits,0,None"
print(t0_ns, ready_msg)
send_msg(ready_msg, t0_ns, 0)


def is_tip_depressed():
    """
    Returns:
        True if tip is found to be depressed/touching (circuit open).
    """
    tip_B_pull_up_pin.switch_to_output(value=True)
    touch = tip_B_sense_pin.value  # foil : circuit opens upon touch.
    tip_B_pull_up_pin.switch_to_input(pull=None)
    # work around for RP2350 errata E9 - the pin latches up without an external
    # pulldown smaller than 8.2K !!
    # since pulling it down to ground changes our protection, i'd rather do this.
    tip_B_sense_pin.switch_to_output(value=False)
    tip_B_sense_pin.switch_to_input(pull=None)
    return touch


min_touch_nsec = settings["min_touch_msec"] * 1e6
touch_i = 0
while True:
    t_now_ns = time.monotonic_ns()
    if is_tip_depressed():
        with analogbufio.BufferedIn(board.GP26, sample_rate=sampling_rate) as adcbuf:
            adcbuf.readinto(adc_read_buffer)
        t_pre = time.monotonic_ns()
        # timed it - took ~ 3 msec for a 500 long buffer. not too awful.
        pow = goertzel_algorithm(
            adc_read_buffer, sample_rate=sampling_rate, target_frequency=target_freq
        )
        # wait for min time to pass before checking (debounce)
        while time.monotonic_ns() - t_now_ns < min_touch_nsec:
            pass
        if not is_tip_depressed():
            print("failed to find tip still pressed after checking validity, no touch.")
            continue
        touch_i += 1
        msg = f"{we_are},touched,{touch_i},{pow >= settings['min_valid_power']}"
        # send, willing to repeat for some amount of time.
        send_msg(msg, t_now_ns, send_touch_for_ns)
        time_since_press_sec = (time.monotonic_ns() - t_now_ns) / 1e9
        print(t_now_ns, time_since_press_sec, msg + f"; {pow=}")
        # print(f"{time_since_press_sec=:0.4f} {dormant_after_hit_sec=:0.2f}")
        sleep_t = dormant_after_hit_sec - time_since_press_sec
        if sleep_t <= 0:
            print(f"{sleep_t=} <= 0; skipping sleep.")
        else:
            print(f"sleeping for {sleep_t:0.3f} sec")
            time.sleep(sleep_t)
        post_announce_t_ns = time.monotonic_ns()
        msg = f"{we_are},Sent hit - slept - back in business,{touch_i},False"
        print(post_announce_t_ns, msg + "\n\n")
        send_msg(msg, post_announce_t_ns)
    else:
        pass
        # print(f"{touch_i=}, no touch")
