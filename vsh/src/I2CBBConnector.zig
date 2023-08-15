const std = @import("std");

const Cxxrtl = @import("./Cxxrtl.zig");
const Tick = @import("./OLEDConnector.zig").Tick;
const RW = @import("./OLEDConnector.zig").RW;
const Sample = @import("./Sample.zig").Sample;

const I2CBBConnector = @This();

addr: u7,

addressed: ?RW = null,
latched_fifo_in_data: u9 = undefined,
next_read_value: u8 = undefined,

in_fifo_w_data: Sample(u9),
in_fifo_w_en: Sample(bool),
stb: Sample(bool),
busy: Sample(bool),

bb_in_ack: Cxxrtl.Object(bool),
bb_in_out_fifo_data: Cxxrtl.Object(u8),
bb_in_out_fifo_stb: Cxxrtl.Object(bool),

pub fn init(cxxrtl: Cxxrtl, addr: u7) I2CBBConnector {
    const in_fifo_w_data = Sample(u9).init(cxxrtl, "oled i2c in_fifo_w_data", 0);
    const in_fifo_w_en = Sample(bool).init(cxxrtl, "oled i2c in_fifo_w_en", false);
    const stb = Sample(bool).init(cxxrtl, "oled i2c stb", false);
    const busy = Sample(bool).init(cxxrtl, "oled i2c busy", false);

    const bb_in_ack = cxxrtl.get(bool, "i_i2c_bb_in_ack");
    const bb_in_out_fifo_data = cxxrtl.get(u8, "i_i2c_bb_in_out_fifo_data");
    const bb_in_out_fifo_stb = cxxrtl.get(bool, "i_i2c_bb_in_out_fifo_stb");

    return .{
        .addr = addr,
        .in_fifo_w_data = in_fifo_w_data,
        .in_fifo_w_en = in_fifo_w_en,
        .stb = stb,
        .busy = busy,
        .bb_in_ack = bb_in_ack,
        .bb_in_out_fifo_data = bb_in_out_fifo_data,
        .bb_in_out_fifo_stb = bb_in_out_fifo_stb,
    };
}

pub fn tick(self: *I2CBBConnector) Tick {
    const in_fifo_w_data = self.in_fifo_w_data.tick();
    const in_fifo_w_en = self.in_fifo_w_en.tick();
    const stb = self.stb.tick();
    const busy = self.busy.tick();

    if (self.bb_in_out_fifo_stb.curr()) {
        self.bb_in_out_fifo_stb.next(false);
    }

    if (in_fifo_w_en.curr) {
        self.latched_fifo_in_data = in_fifo_w_data.curr;

        if (self.addressed) |rw| {
            if ((self.latched_fifo_in_data & 0x100) == 0x100) {
                const next_rw = self.handleAddress(self.latched_fifo_in_data) orelse return .Fish;
                switch (next_rw) {
                    .W => return .AddressedWrite,
                    .R => return .{ .AddressedRead = &self.next_read_value },
                }
            } else {
                switch (rw) {
                    .W => return .{ .Byte = @as(u8, @truncate(self.latched_fifo_in_data)) },
                    .R => {
                        self.bb_in_out_fifo_data.next(self.next_read_value);
                        self.bb_in_out_fifo_stb.next(true);
                        return .Pass;
                    },
                }
            }
        }
    }

    if (stb.rising()) {
        if (self.addressed == null and (self.latched_fifo_in_data & 0x100) == 0x100) {
            const rw = self.handleAddress(self.latched_fifo_in_data) orelse return .Pass;
            switch (rw) {
                .W => return .AddressedWrite,
                .R => {
                    return .{ .AddressedRead = &self.next_read_value };
                },
            }
        }
    }

    if (busy.falling() and self.addressed != null) {
        return .Fish;
    }

    return .Pass;
}

fn handleAddress(self: *I2CBBConnector, fifo: u9) ?RW {
    const addr: u7 = @as(u7, @truncate(fifo >> 1));
    const rw = @as(RW, @enumFromInt(@as(u1, @truncate(fifo))));
    if (addr == self.addr) {
        self.addressed = rw;
        self.bb_in_ack.next(true);
        return rw;
    } else {
        self.bb_in_ack.next(false);
        return null;
    }
}

pub fn reset(self: *I2CBBConnector) void {
    self.addressed = null;
}
