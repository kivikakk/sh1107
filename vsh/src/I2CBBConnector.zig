const std = @import("std");

const Cxxrtl = @import("./Cxxrtl.zig");
const Tick = @import("./OLEDConnector.zig").Tick;
const RW = @import("./OLEDConnector.zig").RW;
const Sample = @import("./Sample.zig").Sample;

const I2CBBConnector = @This();

addr: u7,

addressed: bool = false,
latched_fifo_data: u9 = undefined,

fifo_w_data: Sample(u9),
fifo_w_en: Sample(bool),
stb: Sample(bool),
busy: Sample(bool),
ack_in: Cxxrtl.Object(bool),

pub fn init(cxxrtl: Cxxrtl, addr: u7) I2CBBConnector {
    const fifo_w_data = Sample(u9).init(cxxrtl, "oled i2c fifo_w_data", 0);
    const fifo_w_en = Sample(bool).init(cxxrtl, "oled i2c fifo_w_en", false);
    const stb = Sample(bool).init(cxxrtl, "oled i2c stb", false);
    const busy = Sample(bool).init(cxxrtl, "oled i2c busy", false);
    const ack_in = cxxrtl.get(bool, "i_i2c_ack_in");

    return .{
        .addr = addr,
        .fifo_w_data = fifo_w_data,
        .fifo_w_en = fifo_w_en,
        .stb = stb,
        .busy = busy,
        .ack_in = ack_in,
    };
}

pub fn tick(self: *I2CBBConnector) Tick {
    const fifo_w_data = self.fifo_w_data.tick();
    const fifo_w_en = self.fifo_w_en.tick();
    const stb = self.stb.tick();
    const busy = self.busy.tick();

    if (fifo_w_en.rising()) {
        self.latched_fifo_data = fifo_w_data.curr;

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
