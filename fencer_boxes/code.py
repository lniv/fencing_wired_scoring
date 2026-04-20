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

NOTE: this was used originally with a pico2W i.e. a RP2350:
this required working around errata E9 - the pin latches up without an external
pulldown smaller than 8.2K !!
since the series protection resistor (which ground the pin through the tip) is 20k,
i chose to ground the pin in firmware instead.
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
from ulab import numpy as np
from ulab.utils import from_uint16_buffer, spectrogram


# standardize on using monotonic_ns as integer, and have times in millisec.

print("Reading from settings.toml")
# before we do anything else, lets see that we have a sane definitions file.
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
    "sampling_end_to_min_touch_msec",
    "sampling_time_msec",
    "left_Hz",
    "right_Hz",
    "off_peak_offset_Hz",
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

# i'm going to optimize things to get a power of 2 adc reads
# since the ulab spectrogram requires it in any case.
sampling_rate = settings["sampling_rate_Hz"]
requested_sampling_time_sec = settings["sampling_time_msec"] * 1e-3
pow2_vec = np.array([2**n for n in range(16)])  # enough to ensure cover.
# NOTE: dropping the median filtering. if we decided to add it again,
# we'll need to add the extra 2*half median here.
array_length = int(
    pow2_vec[np.argmin(abs(pow2_vec - sampling_rate * requested_sampling_time_sec))]
)
sampling_time_sec = array_length / sampling_rate
print(
    f"{requested_sampling_time_sec=}, selecting closest 2**n so that {sampling_time_sec=}, {array_length=}"
)
# now find the best match for frequencies.
requested_right_freq = settings["right_Hz"]
requested_left_freq = settings["left_Hz"]
spectrogram_fs = np.linspace(0, sampling_rate / 2, int(array_length / 2 + 1))
right_freq_i = np.argmin(abs(spectrogram_fs - requested_right_freq))
left_freq_i = np.argmin(abs(spectrogram_fs - requested_left_freq))
# casting these since one will be use for a pwm call that takes an integer.
# it's true that these won't be exact, but 0.5 Hz offset seems acceptable.
right_freq = int(spectrogram_fs[right_freq_i])
left_freq = int(spectrogram_fs[left_freq_i])
print(f"Optimized to match spectrogram frequencies")
print(f"{requested_right_freq=} changed to {right_freq=}, {right_freq_i=}")
print(f"{requested_left_freq=} changed to {left_freq=}, {left_freq_i=}")


if we_are == "right":
    out_freq = right_freq
    target_freq = left_freq
    target_freq_i = left_freq_i
elif we_are == "left":
    out_freq = left_freq
    target_freq = right_freq
    target_freq_i = right_freq_i
else:
    raise RuntimeError(
        f"{settings['fencer']=} but we must be FENCER = RIGHT or FENCER = LEFT in settings.toml"
    )

requested_off_peak_offset = settings["off_peak_offset_Hz"]
# rather than look for best below/above indices, which may be not be exactly opposite,
# calculate an optimum delta
delta_i = np.argmin(abs(spectrogram_fs - requested_off_peak_offset))
below_peak_i = target_freq_i - delta_i
above_peak_i = target_freq_i + delta_i

off_peak_freqs = [spectrogram_fs[below_peak_i], spectrogram_fs[above_peak_i]]
print(
    f"Off peak {requested_off_peak_offset=} changed to {off_peak_freqs=}, {below_peak_i=}, {above_peak_i=}"
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

print(
    f"{we_are=}, output at {out_freq} Hz, looking for {target_freq} Hz, {off_peak_freqs=} Hz"
)

# hardware / pin definitions and setup

# connected to lame, through a lowpass filter, so we can do simple square wave.
# low pass will be at ~ 10kHz, so keep frequencies below that.
Lame_A_pin = board.GP13

# we have a resistor connected between the jack and each
# the pull up must be much larger than the protection resistor,
# since that's part of the line going to ground when the tip switch is closed.
# i.e. it won't "allow" it to be pulled to ground otherwise.
tip_B_pull_up_pin = DigitalInOut(board.GP10)  # 100kOhm
tip_B_sense_pin = DigitalInOut(board.GP9)  # 20 kOhm
# set both to high Z to begin.
# actually, i'm going to just have the pull up active
# (i could probably have omitted it and used the built in, but prefer more control.)
tip_B_pull_up_pin.switch_to_output(value=True)
tip_B_sense_pin.switch_to_input(pull=None)


# set up hardare (do this before betwork setup?)
pwm_out = pwmio.PWMOut(
    Lame_A_pin, duty_cycle=2**15, frequency=out_freq, variable_frequency=False
)
print(f"Playing pwm at {out_freq} on {Lame_A_pin}")


# i could make it take e.g. a data class instance, but i'm worried about speed
# and don't want to bother profiling; for now there aren't many messages, so i think ok.
def send_msg(sock, msg: str, t_msg_ns: int, send_for_nanosec: int = 0) -> bool:
    """
    send a message to the display - which will have to parse it; simple string.
    Args:
        sock: socket to use for receiving / sending
        msg: send this to our display.
        t_msg_ns: when it happened, in nanosec.
        send_for_nanosec: will continue sending till t_msg + this expires, randomly.
    Returns:
        True if it managed to get through, False otherwise.
    """
    t_m1_ns = time.monotonic_ns()
    buffer = bytearray(1024)
    print(
        f"Took {(1e-6 * (time.monotonic_ns() - t_m1_ns)):0.1f} msec to create socket."
    )
    n_sent = 0
    try:
        # send once, then if we have time, repeat.
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
            # check if we got something back, if we did, we're done.
            num_bytes, remote_address = sock.recvfrom_into(buffer)
            if num_bytes > 0:
                # should probably check that it came from the right address, and perhaps that something
                # (message id?) was in it. later.
                print(f"Received {buffer[:num_bytes]} from {remote_address}, good.")
                break

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
our_addr_s = str(wifi.radio.ipv4_address)
sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
sock.settimeout(
    0.0011
)  # non blocking. (do we need to handle the exception on timeout?)
sock.bind((our_addr_s, settings["display_port"]))
send_msg(sock, f"{we_are},Just woke up,0,None,None", time.monotonic_ns())


############## end network stuff
# future / TODO: heartbeat to display / server, get time sync from server?
detection_to_sampling_sec = (
    settings["min_touch_msec"] - settings["sampling_end_to_min_touch_msec"]
) * 1e-3 - sampling_time_sec
print(
    f"Will wait for {detection_to_sampling_sec} before sampling for {sampling_time_sec=}."
)

# # i'm going to run a median filter on the data, and do a linear fit subtraction.
# median_half_span = 2
# data_post_median_filt_indices = list(
#     range(median_half_span, array_length - median_half_span)
# )
# median_filtered_length = array_length - 2 * median_half_span
# t_vec = np.linspace(0, median_filtered_length / sampling_rate, median_filtered_length)
print(f"sampling for {sampling_time_sec=}, {sampling_rate=}, N={array_length}")
adc_read_buffer = array.array("H", [0x0000] * array_length)

t0_ns = time.monotonic_ns()
ready_msg = f"{we_are},now in business - looking for hits,0,None,None"
print(t0_ns, ready_msg)
send_msg(sock, ready_msg, t0_ns, 0)


def reset_tip_state(ground_sec=0.001, delay_after_sec=0, repeats=1):
    """
    I'm getting repeat phantom touches, which i suspect are the rp2350 bug.
    the normal check does this momentarily, but we can afford to wait much longer after a touch
    (whether is_tip_depressed should as well, maybe)
    TODO: i should make this dependent on whether the board is an rp2350.
    """
    # work around for RP2350 errata E9 - the pin latches up without an external
    # pulldown smaller than 8.2K !!
    # since pulling it down to ground changes our protection, i'd rather do this.
    for _i in range(repeats):
        tip_B_sense_pin.switch_to_output(value=False)
        if ground_sec > 0:
            time.sleep(ground_sec)
        tip_B_sense_pin.switch_to_input(pull=None)
        if delay_after_sec > 0:
            time.sleep(delay_after_sec)


def is_tip_depressed(ground_sense_sec=0.003):
    """
    foil specific ; if we branch in the future, we'll define this based on weapon.
    NOTE: i've moved out any workaround for RP2350 latchup out of this.
    Args:
        ground_sense_sec: if positive, sleep with tip pulled down for this long [0.003]
    Returns:
        True if tip is found to be depressed/touching (circuit open).
    """
    return tip_B_sense_pin.value  # foil : circuit opens upon touch.


min_touch_nsec = settings["min_touch_msec"] * 1e6
touch_i = 1
while True:
    # this section till we evaluate the ADC buffer should be in a weapon dependent function.
    print(f"Waiting before {touch_i=}")
    # wait for touch, busy loop, doing nothing else to get maximal responsiveness.
    while not is_tip_depressed():
        pass
    t_now_ns = time.monotonic_ns()
    # drop the pullup, let the input float, so we don't rail things now.
    tip_B_pull_up_pin.switch_to_input(pull=None)
    # # maybe try grounding the source for some amount of time before looking for the ac signal?

    # wait some amount of time, then record vector (and a short one - it seemed best to wait more!)
    if detection_to_sampling_sec > 0:
        time.sleep(detection_to_sampling_sec)
    # now record.
    with analogbufio.BufferedIn(board.GP26, sample_rate=sampling_rate) as adcbuf:
        adcbuf.readinto(adc_read_buffer)
    reset_tip_state(ground_sec=0.001, delay_after_sec=0, repeats=1)
    # now reactivate the pull up line.
    tip_B_pull_up_pin.switch_to_output(value=True)
    # now wait till min touch time has passed.
    print(f"since touch {(time.monotonic_ns() - t_now_ns)/1e6} msec")
    while time.monotonic_ns() - t_now_ns < min_touch_nsec:
        pass
    # check if the tip is still pressed.
    # (making it more foil specific for now, will need to refactor later for e.g. epee)
    if not is_tip_depressed():
        print("failed to find tip still pressed after checking validity, no touch.")
        continue
    # we have a valid touch, analyze data now.
    # calculate power at two frequencies
    # if this doesn't work (and it didn't do great before), will have to do pseudo -random,
    # or split the lame generation from the detection much harder (e.g. separate hardware)
    t_analysis_start_ns = time.monotonic_ns()
    data = from_uint16_buffer(
        adc_read_buffer
    )  # faster than np.array(adc_read_buffer) ?
    ss = spectrogram(data)
    pow = ss[target_freq_i]
    # use simple mean of the above and below peak frequencies.
    off_peak_pow = 0.5 * (ss[below_peak_i] + ss[above_peak_i])

    t_analysis_end_ns = time.monotonic_ns()
    print(f"Analysis too {t_analysis_end_ns - t_analysis_start_ns} nanosec")
    # moving the validity call to the display / control side.
    # i avoided it in the past to shorten cycle time, but timing it at 0.2 msec on an esp32-s3
    # in circuitpython, even with float conversions, so acceptable for now and makes debugging
    # easier.
    msg = f"{we_are},touched,{touch_i},{pow},{off_peak_pow}"
    # send, willing to repeat for some amount of time.
    send_msg(sock, msg, t_now_ns, send_touch_for_ns)
    time_since_press_sec = (time.monotonic_ns() - t_now_ns) / 1e9
    # print(t_now_ns, time_since_press_sec, msg + f"; {pow=}")
    print(t_now_ns, time_since_press_sec, msg)
    # print(f"{time_since_press_sec=:0.4f} {dormant_after_hit_sec=:0.2f}")
    sleep_t = dormant_after_hit_sec - time_since_press_sec
    if sleep_t <= 0:
        print(f"{sleep_t=} <= 0; skipping sleep.")
    else:
        print(f"sleeping for {sleep_t:0.3f} sec")
        repeats = int(sleep_t / 0.01)
        reset_tip_state(ground_sec=0, delay_after_sec=0.01, repeats=repeats)
    post_announce_t_ns = time.monotonic_ns()
    msg = f"{we_are},Sent hit - slept - back in business,{touch_i},None,None"
    print(post_announce_t_ns, msg + "\n\n")
    send_msg(sock, msg, post_announce_t_ns)
    touch_i += 1
