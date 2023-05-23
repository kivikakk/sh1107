const std = @import("std");

const Cxxrtl = @import("./Cxxrtl.zig");
const Tick = @import("./OLEDConnector.zig").Tick;
const RW = @import("./OLEDConnector.zig").RW;
const Value = @import("./Value.zig").Value;
const track = @import("./Value.zig").track;

const I2CBBConnector = @This();

addr: u7,

addressed: bool = false,

latched_fifo_data: u9 = undefined,

fifo_w_data: Cxxrtl.Object(u9),
fifo_w_data_prev: u9 = 0,

fifo_w_en_prev: bool = false,
fifo_w_en: Cxxrtl.Object(bool),

stb: Cxxrtl.Object(bool),
stb_prev: bool = false,

ack_in: Cxxrtl.Object(bool),

busy: Cxxrtl.Object(bool),
busy_prev: bool = false,

pub fn init(cxxrtl: Cxxrtl, addr: u7) I2CBBConnector {
    const fifo_w_data = cxxrtl.get(u9, "oled i2c fifo_w_data");
    const fifo_w_en = cxxrtl.get(bool, "oled i2c fifo_w_en");
    const stb = cxxrtl.get(bool, "oled i2c stb");
    const ack_in = cxxrtl.get(bool, "i2c_i_ack_in");
    const busy = cxxrtl.get(bool, "oled i2c busy");

    return .{
        .addr = addr,
        .fifo_w_data = fifo_w_data,
        .fifo_w_en = fifo_w_en,
        .stb = stb,
        .ack_in = ack_in,
        .busy = busy,
    };
}

pub fn tick(self: *I2CBBConnector) Tick {
    const fifo_w_data = track(self, u9, "fifo_w_data");
    const fifo_w_en = track(self, bool, "fifo_w_en");
    const stb = track(self, bool, "stb");
    const busy = track(self, bool, "busy");

    if (fifo_w_en.rising()) {
        self.latched_fifo_data = fifo_w_data.value;

        if (self.addressed) {
            if ((self.latched_fifo_data & 0x100) == 0x100) {
                return if (self.handleAddress(self.latched_fifo_data)) .Addressed else .Fish;
            } else {
                return .{ .Byte = @truncate(u8, self.latched_fifo_data) };
            }
        }
    }

    if (stb.rising()) {
        if (!self.addressed and (self.latched_fifo_data & 0x100) == 0x100) {
            return if (self.handleAddress(self.latched_fifo_data)) .Addressed else .Pass;
        }
    }

    if (busy.falling() and self.addressed) {
        return .Fish;
    }

    return .Pass;
}

fn handleAddress(self: *I2CBBConnector, fifo: u9) bool {
    self.ack_in.next(false);

    const addr: u7 = @truncate(u7, fifo >> 1);
    const rw = @intToEnum(RW, @truncate(u1, fifo));
    if (addr == self.addr and rw == .W) {
        self.addressed = true;
        self.ack_in.next(true);
        return true;
    } else if (addr == self.addr and rw == .R) {
        std.debug.print("NYI: read\n", .{});
        return false;
    } else {
        return false;
    }
}

pub fn reset(self: *I2CBBConnector) void {
    self.addressed = false;
}
