# A simple fencing scoring system

The aim is to make it simple, rather than efficient or super precise.\
Towards that, the hardware is a LED display with a matching controller from adafruit,
and circuitpython is used vs e.g. C. I tried to keep hardware to minimum, but pullup resisotrs appear necesssary,

Note: foil only currently.

adding a wireless option - this relies on fencer side boxes, obviously, which are still in a separate repo.

## Setup
- Install circuitpython on the matrixportal S3 : https://learn.adafruit.com/adafruit-matrixportal-s3/install-circuitpython
- Prep the portal and led display : https://learn.adafruit.com/adafruit-matrixportal-s3/prep-the-matrixportal
### Wired setup:
- Solder 2.2kohm (or similar) pullup resistors between the two weapon lines and 3V on the matriportalS3.
- Solder a buzzer between the A0 (battery connector) and ground.
- Copy code.py and the various bmp files onto the circuitpython drive.
- Print [display_connector.step](hardware/display_connector.step) and 2 or 3 of [display_leg](hardware/display_leg.step), and use a few M3x12 screws attach to display.

### Wireless setup
- You'd need the fencer boxes, TBA (duh); no need for the banana jacks or the pullup resistors on the display side.
- The settings.toml file should be copied onto the circuitpython drive, as well as the lib folder.
- The display will create an AP with the ssid/password defined in the toml file - the default is ok for a single box.

### Common
- Power from a usb-c supply ; i'm unsure what's the minimum power needed.
- Fence.
