const gk = @import("gamekit");

const DclkFreq = enum(i7) {
    Neg25 = -25,
    Neg20 = -20,
    Neg15 = -15,
    Neg10 = -10,
    Neg5 = -5,
    Zero = 0,
    Pos5 = 5,
    Pos10 = 10,
    Pos15 = 15,
    Pos20 = 20,
    Pos25 = 25,
    Pos30 = 30,
    Pos35 = 35,
    Pos40 = 40,
    Pos45 = 45,
    Pos50 = 50,
};

const AddrMode = enum {
    Page,
    Column,

    pub fn str(self: AddrMode) []const u8 {
        return switch (self) {
            .Page => "page",
            .Column => "column",
        };
    }
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
