const std = @import("std");
const gk = @import("gamekit");

const Cmd = @import("./Cmd.zig");

pub const DclkFreq = enum(u4) {
    Neg25 = 0b000,
    Neg20 = 0b001,
    Neg15 = 0b010,
    Neg10 = 0b011,
    Neg5 = 0b0100,
    Zero = 0b0101,
    Pos5 = 0b0110,
    Pos10 = 0b0111,
    Pos15 = 0b1000,
    Pos20 = 0b1001,
    Pos25 = 0b1010,
    Pos30 = 0b1011,
    Pos35 = 0b1100,
    Pos40 = 0b1101,
    Pos45 = 0b1110,
    Pos50 = 0b1111,

    pub fn int(self: DclkFreq) i7 {
        switch (self) {
            .Neg25 => -25,
            .Neg20 => -20,
            .Neg15 => -15,
            .Neg10 => -10,
            .Neg5 => -5,
            .Zero => 0,
            .Pos5 => 5,
            .Pos10 => 10,
            .Pos15 => 15,
            .Pos20 => 20,
            .Pos25 => 25,
            .Pos30 => 30,
            .Pos35 => 35,
            .Pos40 => 40,
            .Pos45 => 45,
            .Pos50 => 50,
        }
    }
};

pub const AddrMode = enum(u1) {
    Page = 0b0,
    Column = 0b1,

    pub fn str(self: AddrMode) []const u8 {
        return switch (self) {
            .Page => "page",
            .Column => "column",
        };
    }
};

pub const SegRemap = enum(u1) {
    Normal = 0b0,
    Flipped = 0b1,
};

pub const COMScanDir = enum(u1) {
    Forwards = 0b0,
    Backwards = 0b1,
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
page_address: u4 = 0,
column_address: u7 = 0,
addressing_mode: AddrMode = .Page,
multiplex: u8 = 128,
segment_remap: SegRemap = .Normal,
com_scan_dir: COMScanDir = .Forwards,

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
            self.segment_remap = adc;
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
            self.start_column = offset;
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
        .SetCommonOutputScanDirection => |direction| {
            self.com_scan_dir = direction;
        },
        .SetDisplayClockFrequency => |cf| {
            self.dclk_freq = cf.frequency;
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
            self.start_line = column;
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

const Write = struct {
    column: u7,
    row: u7,
    value: u8,
};

pub fn data(self: *@This(), b: u8) Write {
    const i2c_width = 128;
    const i2c_height = 128;
    const page_count = i2c_height / 8;

    // ensure we can rely entirely on wrapping addition
    comptime std.debug.assert(i2c_width - 1 == std.math.maxInt(@TypeOf(self.column_address)));
    comptime std.debug.assert(page_count - 1 == std.math.maxInt(@TypeOf(self.page_address)));

    defer switch (self.addressing_mode) {
        .Page => self.column_address +%= 1,
        .Column => self.page_address +%= 1,
    };

    var row: u7 = undefined;
    var value: u8 = 0;

    switch (self.segment_remap) {
        .Normal => {
            row = @as(u7, self.page_address) * 8;

            var i: u4 = 8;
            while (i > 0) : (i -= 1) {
                value = (value << 1) | ((b >> @truncate(u3, i - 1)) & 0x1);
            }
        },
        .Flipped => {
            row = (@as(u7, page_count) - self.page_address - 1) * 8;

            var i: u4 = 0;
            while (i < 8) : (i += 1) {
                value = (value << 1) | ((b >> @truncate(u3, i)) & 0x1);
            }
        },
    }

    return .{
        .column = self.column_address,
        .row = row,
        .value = value,
    };
}
