# Fencer boxes used for a wireless setup

Obviously you'd need two of these. Oveall, they're a combination of a picow (RP2040 based) or pico2w (RP2350 based) with a custom front end.

## Hardware setup
* make a front end (duh). The schematics and layout for the front end are in [here](./front_end).
    * The front end is not tightly tied to the pico(2) pinout, though the code is. The current design uses a TSSOP opamp, which is a bit challenging to solder manually, but the other components were kept to 0805 mostly. The setup is simple enough that it could be built on a generic TSSOP adapter, but at 1$/board throush oshpark, why bother.
    * Wiring for a pico-w/pico2-w:
        * 8 pin header:
            * 1 : Not connected
            * 2 : ground
            * 3 : 3.3V
            * 4 : GP9 (tip sense line)
            * 5 : Not connected
            * 6 : GP10 (tip pullup line)
            * 7 : GP13 (lame drive)
            * 8 : GP26/A0 (lame sense)
        * 3 pin header:
            * 1 : A (lame)
            * 2 : B (weapon / tip)
            * 3 : C (ground / common)
* I typically CA glue them to the pico and wire the connections.
* Have a mechanical setup with the three banana jacks, wired to the front end
* power is via the micro usb connector - I use a small usb battery pack.

## Software setup
* Install circuitpython onto the board; for a pico2w, [https://circuitpython.org/board/raspberry_pi_pico2_w/]
* copy [code.py](./code.py) onto the board
* copy the [settings.toml from the parent folder](../settings.toml) file onto the board AND modify it to select either "left" or "right" side.

## TODO:
* Add step files for suitable hardware boxes
* Add BOM
* Replace opamp with a soic part. 
