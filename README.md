# A simple fencing scoring system

The aim is to make it simple, rather than efficient or super precise.\
Towards that, the hardware is a LED display with a matching controller from adafruit,
and circuitpython is used vs e.g. C. I tried to keep hardware to minimum, but pullup resisotrs appear necesssary for wired operation.

Note: foil only currently.

## Setup

### Display

#### Common to wired and wireless setups

These instructions assume a matrixportal-S3 is used as the display controller. There is nothing magical about it, but it is convenient.

- Install circuitpython on the matrixportal S3 : https://learn.adafruit.com/adafruit-matrixportal-s3/install-circuitpython
- Prep the portal and led display : https://learn.adafruit.com/adafruit-matrixportal-s3/prep-the-matrixportal
- Wire a buzzer between the A0 (battery connector) and ground.
- Copy [code.py](./code.py), [settings.toml](./settings.toml) and the various bmp files onto the circuitpython drive.

#### Additional display / connector setup for wired use:

I added the wireless option later, so e.g. the display legs or buzzer holder were integrated with parts that are necessary only for wired operation.

- Solder 2.2kohm (or similar) pullup resistors between the two weapon lines and 3V on the matriportalS3. These may not be necessary if you're using a different controller, in which case you should disable the pullup option ("HAVE_EXTERNAL_PULLUPS") in the settings.toml file.
- Print [display_connector.step](hardware/display_connector.step) and 2 or 3 of [display_leg](hardware/display_leg.step), and use a few M3x12 screws attach to display.
- Install and wire the six banana jacks.

### Wireless setups
- The two fencer boxes are described [here](./fencer_boxes/README.md).
- The display will create an AP with the ssid/password defined in the toml file - the default is ok for a single box.
- The three boxes can be powered on at any order, but if a fencer box doesn't find the AP, it will wait 5 sec before retrying, so if powered first you may have a 10 sec delay before hits can be registered.

## Usage
- Power display (and fencer boxes if used) via usb (typc-c, micro) connectors. The display likely needs ~ 10W.
- The display will setup up an AP (and operated in wireless mode) if the configuration file is deemed valid for wireless operation.
    - This can be overridden by holding the down button at startup.
- Audio can be enabled / disabled by holding the down button while a tip is pressed.
- Fence.
