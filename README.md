# A simple wired fencing scoring system

The aim is to make it simple, rather than efficient or super precise.\
Towards that, the hardware is a LED display with a matching controller from adafruit,
and circuitpython is used vs e.g. C. I tried to keep hardware to minimum, but pullup resisotrs appear necesssary,

Note: foil only currently.

## Setup
- Install circuitpython on the matrixportal S3 : https://learn.adafruit.com/adafruit-matrixportal-s3/install-circuitpython
- Prep the portal and led display : https://learn.adafruit.com/adafruit-matrixportal-s3/prep-the-matrixportal
- Solder 2.2kohm (or similar) pullup resistors between the two weapon lines and 3V on the matriportalS3.
- Solder a buzzer between the A0 (battery connector) and ground (to be tested).
- Copy code.py and the various bmp files onto the circuitpython drive.
- Print [display_connector.step](hardware/display_connector.step) and 2 or 3 of [display_leg](hardware/display_leg.step), and use a few M3x12 screws attach to display.
- Power from a usb-c supply ; i'm unsure what's the minimum power needed.
- Fence.
