const gk = @import("gamekit");

const Cmd = @import("./Cmd.zig");

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

pub fn cmd(self: *@This(), c: Cmd.Command) void {
    switch (c) {
        .SetLowerColumnAddress => |lower| {
            self.column_address = (self.column_address & 0x70) | lower;
        },
        .SetHigherColumnAddress => |higher| {
            self.column_address = (self.column_address & 0x0F) | (@as(u7, higher) << 4);
        },
        .SetMemoryAddressingMode => |mode| {
            self.addressing_mode = mode;
        },
        .SetContrastControlRegister => |level| {
            self.contrast = level;
        },
        .SetSegmentRemap => |adc| {
            self.segment_remap = adc == .Flipped;
        },
        .SetMultiplexRatio => |ratio| {
            self.multiplex = ratio;
        },
        .SetEntireDisplayOn => |on| {
            self.all_on = on;
        },
        .SetDisplayReverse => |reverse| {
            self.reversed = reverse;
        },
        .SetDisplayOffset => |offset| {
            self.start_line = offset;
        },
        .SetDCDC => |on| {
            self.dcdc = on;
        },
        .DisplayOn => |on| {
            self.power = on;
        },
        .SetPageAddress => |page| {
            self.page_address = page;
        },
        .SetCommonScanOutputDirection => |direction| {
            self.com_scan_reversed = direction == .Backwards;
        },
        .SetDisplayClockFrequency => |cf| {
            self.dclk_freq = cf.freq;
            self.dclk_ratio = cf.ratio;
        },
        .SetPreDischargePeriod => |predis| {
            self.precharge_period = predis.precharge;
            self.discharge_period = predis.discharge;
        },
        .SetVCOMDeselectLevel => |level| {
            self.vcom_desel = level;
        },
        .SetDisplayStartColumn => |column| {
            self.start_column = column;
        },
        .ReadModifyWrite => {
            @panic("not impl");
        },
        .End => {
            @panic("not impl");
        },
        .Nop => {
            // pass
        },
    }
}

pub fn data(self: *@This(), b: u8) void {
    _ = b;
    _ = self;
    // TODO
    @panic("not impl");
    // page_count = self.I2C_HEIGHT // 8
    // for b in data:
    //     for i in range(7, -1, -1):
    //         if not self.segment_remap:
    //             pa = self.page_address * 8 + i
    //         else:
    //             pa = (page_count - self.page_address - 1) * 8 + (7 - i)
    //         self.set_px(
    //             self.column_address,
    //             pa,
    //             1 if ((b >> i) & 0x01) == 0x01 else 0,
    //         )
    //     if (
    //         self.addressing_mode
    //         == Cmd.SetMemoryAddressingMode.Mode.Page
    //     ):
    //         self.column_address = (
    //             self.column_address + 1
    //         ) % self.I2C_WIDTH
    //     else:
    //         self.page_address = (self.page_address + 1) % page_count

}
