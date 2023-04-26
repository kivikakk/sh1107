const gk = @import("gamekit");

const DclkFreq = enum {
    Neg25,
    Neg20,
    Neg15,
    Neg10,
    Neg5,
    Zero,
    Pos5,
    Pos10,
    Pos15,
    Pos20,
    Pos25,
    Pos30,
    Pos35,
    Pos40,
    Pos45,
    Pos50,
};

const AddrMode = enum {
    Page,
    Column,
};

power: bool = false,
dcdc: bool = true,
dclk_freq: DclkFreq = .Zero,
dclk_ratio: u8 = 1,
precharge_period: u4 = 2,
discharge_period: u4 = 2,
vcom_desel: u8 = 0x35,
all_on: bool = false,
reversed: bool = false,
contrast: u8 = 0x80,
start_line: u7 = 0,
start_column: u7 = 0,
page_address: u7 = 0,
column_address: u7 = 0,
addressing_mode: AddrMode = .Page,
multiplex: u8 = 128,
segment_remap: bool = false,
com_scan_reversed: bool = false,

pub fn init() @This() {
    return .{};
}
