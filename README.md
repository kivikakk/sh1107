# sh1107

[![Build status](https://badge.buildkite.com/50b21967ee2e88d80db0bd35a97173a66f322b5d2141d21060.svg)](https://buildkite.com/hrzn/sh1107)

Chawwo!

I'm just learning to write gateware. This repository is a testbed for exploring
[Amaranth](https://github.com/amaranth-lang/amaranth) while doing so. It
contains an I²C controller, plus a basic controller for SH1107-type OLEDs over
I²C, such as the [Pimoroni 1.12" 128x128 monochrome
OLED](https://shop.pimoroni.com/products/1-12-oled-breakout). The controller
supports simple commands akin to old BASIC: `CLS`, `PRINT`, `LOCATE`. The old
IBM 8x8 font is used to this end.

There's a driver in the root which exposes the various things it can do:

```console
$ ./driver.py -h
usage: driver [-h] {test,formal,build,rom,vsh} ...

positional arguments:
  {test,formal,build,rom,vsh}
    test                run the unit tests and sim tests
    formal              formally verify the design
    build               build the design, and optionally program it
    rom                 build the ROM image, and optionally program it
    vsh                 run the Virtual SH1107

options:
  -h, --help            show this help message and exit
```

TODOs:

- Formal verification of some key components
- Read the ROM image (with command sequences and character data) from the flash
  over SPI (currently just encoded into the bitstream)
- ?

The current test deployment target is the iCEBreaker ([Crowd
Supply](https://www.crowdsupply.com/1bitsquared/icebreaker-fpga),
[1BitSquared](https://1bitsquared.com/products/icebreaker)). Connect PMOD1 A1 to
SDA, A2 to SCL.

Maybe the most interesting thing right now is the Virtual SH1107 for testing the
gateware. It emulates the internal state of the SH1107 device — what you see
rendered is what you should see on the display.

[<img alt="screenshot of the Virtual SH1107 testbench" src="doc/vsh.png"
height="300">](doc/vsh.png) [<img alt="photo of the OLED device being run on an
iCEBreaker" src="doc/helloworld.jpg" height="300">](doc/helloworld.jpg)

Initially this was implemented in Python and ran cooperatively with Amaranth's
own simulator, like the unit tests, but it was pretty slow. It's now written in
[Zig](https://ziglang.org), and interacts with the simulated hardware running on
its own thread by compiling it to C++ through Yosys's [CXXRTL
backend](https://github.com/YosysHQ/yosys/tree/master/backends/cxxrtl).

At the most fine-grained level (`vsh -i`), it responds to the gateware just
somewhat permissively — edge detection at I²C level. This method is less slow
than the pure Python version.

By default, though, the I²C circuit is stubbed out with a
[blackbox](vsh/i2c_blackbox.cc) that acts close enough to the real controller
for the rest of the design, and the Virtual SH1107 spies on the inputs to the
blackbox directly. This is _much_ faster.
