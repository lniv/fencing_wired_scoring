# A simple fencing scoring system

The aim is to make it simple, rather than efficient or super precise.\
Towards that, the hardware is a LED display with a matching controller from adafruit,
and circuitpython is used vs e.g. C. I tried to keep hardware to minimum, but pullup resisotrs appear necesssary,

Note: foil only currently.

adding a wireless option - this relies on fencer side boxes, obviously, which are still in a separate repo.

## Setup

### Display

#### Common to wired and wireless setups
- Install circuitpython on the matrixportal S3 : https://learn.adafruit.com/adafruit-matrixportal-s3/install-circuitpython
- Prep the portal and led display : https://learn.adafruit.com/adafruit-matrixportal-s3/prep-the-matrixportal
- Wire a buzzer between the A0 (battery connector) and ground.
- Copy [code.py](./code.py), [settings.toml](./settings.toml) and the various bmp files onto the circuitpython drive.

#### Additional display / connector setup for wired use:
- Solder 2.2kohm (or similar) pullup resistors between the two weapon lines and 3V on the matriportalS3.
- Print [display_connector.step](hardware/display_connector.step) and 2 or 3 of [display_leg](hardware/display_leg.step), and use a few M3x12 screws attach to display
- Install and wire the six banana jacks.

### Wireless setups
- The two fencer boxes are described [here](./fencer_boxes/README.md).
- The display will create an AP with the ssid/password defined in the toml file - the default is ok for a single box.

## Usage
- Power display (and fencer boxes if used) via usb (typc-c, micro) connectors. The display likely needs ~ 10W.
- Fence.
