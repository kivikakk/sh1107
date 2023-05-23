const std = @import("std");

const Cxxrtl = @import("./Cxxrtl.zig");

const I2CBBConnector = @This();

addr: u7,

addressed: bool = false,

latched_fifo_data: u9 = undefined,

fifo_w_data: Cxxrtl.Object(u9),
fifo_w_en: Cxxrtl.Object(bool),
stb: Cxxrtl.Object(bool),

busy: Cxxrtl.Object(bool),
busy_prev: bool = false,

fifo_w_data_prev: u9 = 0,
fifo_w_en_prev: bool = false,
stb_prev: bool = false,

pub fn init(cxxrtl: Cxxrtl, addr: u7) I2CBBConnector {
    const fifo_w_data = cxxrtl.get(u9, "oled i2c fifo_w_data");
    const fifo_w_en = cxxrtl.get(bool, "oled i2c fifo_w_en");
    const stb = cxxrtl.get(bool, "oled i2c stb");
    const busy = cxxrtl.get(bool, "oled i2c busy");

    return .{
        .addr = addr,
        .fifo_w_data = fifo_w_data,
        .fifo_w_en = fifo_w_en,
        .stb = stb,
        .busy = busy,
    };
}

const Tick = union(enum) {
    Pass,
    Addressed,
    Error,
    Fish,
    Byte: u8,
};

const RW = enum(u1) {
    W = 0,
    R = 1,
};

pub fn tick(self: *I2CBBConnector) Tick {
    const fifo_w_data = self.track(u9, "fifo_w_data");
    const fifo_w_en = self.track(bool, "fifo_w_en");
    const stb = self.track(bool, "stb");
    const busy = self.track(bool, "busy");
    // if (!fifo_w_data.stable()) {
    //     std.debug.print("fifo_w_data: {}\n", .{fifo_w_data});
    // }
    // if (!fifo_w_en.stable()) {
    //     std.debug.print("fifo_w_en: {}\n", .{fifo_w_en});
    // }
    // if (!stb.stable()) {
    //     std.debug.print("stb: {}\n", .{stb});
    // }
    if (!busy.stable()) {
        std.debug.print("busy: {}\n", .{busy});
    }

    if (fifo_w_en.rising()) {
        std.debug.print("latching fifo_w_data: {x:0>3}\n", .{fifo_w_data.value});
        self.latched_fifo_data = fifo_w_data.value;
    }

    if (stb.rising()) {
        std.debug.print("strobed: fifo has {x:0>3}\n", .{self.latched_fifo_data});
    }

    return .Pass;

    // switch (result) {
    //     .Pass => return .Pass,
    //     .AckNack => {
    //         const byte = self.byte_receiver.byte;
    //         if (!self.addressed) {
    //             const addr: u7 = @truncate(u7, byte >> 1);
    //             const rw = @intToEnum(RW, @truncate(u1, byte));
    //             if (addr == self.addr and rw == .W) {
    //                 self.sda_i.next(false);
    //                 self.addressed = true;
    //                 return .Addressed;
    //             } else if (addr == self.addr and rw == .R) {
    //                 std.debug.print("NYI: read\n", .{});
    //                 return .Pass;
    //             } else {
    //                 return .Pass;
    //             }
    //         } else {
    //             self.sda_i.next(false);
    //             return .{ .Byte = byte };
    //         }
    //     },
    //     .ReleaseSda => {
    //         self.sda_i.next(true);
    //         return .Pass;
    //     },
    //     .Error => {
    //         self.sda_i.next(true);
    //         std.debug.print("got error, resetting\n", .{});
    //         self.addressed = false;
    //         return .Error;
    //     },
    //     .Fish => {
    //         self.sda_i.next(true);
    //         if (!self.addressed) {
    //             std.debug.print("command parser fish while unaddressed\n", .{});
    //         }
    //         self.addressed = false;
    //         return .Fish;
    //     },
    // }
}

pub fn reset(self: *I2CBBConnector) void {
    self.addressed = false;
}

fn Value(comptime T: type) type {
    return struct {
        const Self = @This();

        value: T,
        prev: T,

        inline fn stable(self: Self) bool {
            return self.value == self.prev;
        }

        pub fn format(value: Self, comptime fmt: []const u8, options: std.fmt.FormatOptions, writer: anytype) !void {
            _ = options;
            _ = fmt;
            return std.fmt.format(writer, "{} -> {}", .{
                value.prev,
                value.value,
            });
        }

        usingnamespace if (T == bool) struct {
            inline fn rising(self: Self) bool {
                return self.value and !self.prev;
            }
        } else struct {};
    };
}

fn track(self: *I2CBBConnector, comptime T: type, comptime field: []const u8) Value(T) {
    const value = @field(self, field).curr();
    defer @field(self, field ++ "_prev") = value;

    const prev = @field(self, field ++ "_prev");

    return .{ .value = value, .prev = prev };
}
