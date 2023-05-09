const std = @import("std");

const Cxxrtl = @import("./Cxxrtl.zig");

addr: u7,

byte_receiver: ByteReceiver = .{},
addressed: bool = false,

scl_o: Cxxrtl.Object(bool),
scl_oe: Cxxrtl.Object(bool),
sda_o: Cxxrtl.Object(bool),
sda_oe: Cxxrtl.Object(bool),
sda_i: Cxxrtl.Object(bool),

scl_o_prev: bool = false,
scl_oe_prev: bool = false,
sda_o_prev: bool = false,
sda_oe_prev: bool = false,

pub fn init(cxxrtl: Cxxrtl, addr: u7) @This() {
    const scl_o = cxxrtl.get(bool, "scl__o");
    const scl_oe = cxxrtl.get(bool, "scl__oe");
    const sda_o = cxxrtl.get(bool, "sda__o");
    const sda_oe = cxxrtl.get(bool, "sda__oe");
    const sda_i = cxxrtl.get(bool, "sda__i");

    return .{
        .addr = addr,
        .scl_o = scl_o,
        .scl_oe = scl_oe,
        .sda_o = sda_o,
        .sda_oe = sda_oe,
        .sda_i = sda_i,
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

pub fn tick(self: *@This()) Tick {
    const scl_o = self.track("scl_o");
    const scl_oe = self.track("scl_oe");
    const sda_o = self.track("sda_o");
    const sda_oe = self.track("sda_oe");

    const result = self.byte_receiver.process(scl_o, scl_oe, sda_o, sda_oe);
    switch (result) {
        .Pass => return .Pass,
        .AckNack => {
            const byte = self.byte_receiver.byte;
            if (!self.addressed) {
                const addr: u7 = @truncate(u7, byte >> 1);
                const rw = @intToEnum(RW, @truncate(u1, byte));
                if (addr == self.addr and rw == .W) {
                    self.sda_i.next(false);
                    self.addressed = true;
                    return .Addressed;
                } else if (addr == self.addr and rw == .R) {
                    std.debug.print("NYI: read\n", .{});
                    return .Pass;
                } else {
                    return .Pass;
                }
            } else {
                self.sda_i.next(false);
                return .{ .Byte = byte };
            }
        },
        .ReleaseSda => {
            self.sda_i.next(true);
            return .Pass;
        },
        .Error => {
            self.sda_i.next(true);
            std.debug.print("got error, resetting\n", .{});
            self.addressed = false;
            return .Error;
        },
        .Fish => {
            self.sda_i.next(true);
            if (!self.addressed) {
                std.debug.print("command parser fish while unaddressed\n", .{});
            }
            self.addressed = false;
            return .Fish;
        },
    }
}

pub fn reset(self: *@This()) void {
    self.addressed = false;
}

const Value = struct {
    value: bool,
    stable: bool,

    inline fn stable_high(self: Value) bool {
        return self.stable and self.value;
    }

    inline fn stable_low(self: Value) bool {
        return self.stable and !self.value;
    }

    inline fn falling(self: Value) bool {
        return !self.stable and !self.value;
    }

    inline fn rising(self: Value) bool {
        return !self.stable and self.value;
    }

    pub fn format(value: Value, comptime fmt: []const u8, options: std.fmt.FormatOptions, writer: anytype) !void {
        _ = options;
        _ = fmt;
        return std.fmt.format(writer, "{} -> {}", .{
            if (value.stable) value.value else !value.value,
            value.value,
        });
    }
};

fn track(self: *@This(), comptime field: []const u8) Value {
    const value = @field(self, field).curr();
    defer @field(self, field ++ "_prev") = value;

    const prev = @field(self, field ++ "_prev");

    return .{ .value = value, .stable = value == prev };
}

const ByteReceiver = struct {
    state: enum {
        IDLE,
        START_SDA_LOW,
        WAIT_BIT_SCL_RISE,
        WAIT_BIT_SCL_FALL,
        WAIT_ACK_SCL_RISE,
        WAIT_ACK_SCL_FALL,
    } = .IDLE,
    bits: u4 = 0,
    byte: u8 = 0,

    const Result = enum {
        Pass,
        AckNack,
        ReleaseSda,
        Error,
        Fish,
    };

    fn process(self: *ByteReceiver, scl_o: Value, scl_oe: Value, sda_o: Value, sda_oe: Value) Result {
        const all_stable = scl_oe.stable and scl_o.stable and sda_oe.stable and sda_o.stable;

        switch (self.state) {
            .IDLE => {
                if (scl_oe.stable_high() and scl_o.stable_high() and sda_oe.stable_high() and sda_o.falling()) {
                    self.state = .START_SDA_LOW;
                    self.bits = 0;
                    self.byte = 0;
                    return .ReleaseSda;
                }
            },
            .START_SDA_LOW => {
                if (scl_oe.stable_high() and scl_o.falling() and sda_oe.stable_high() and sda_o.stable_low()) {
                    self.state = .WAIT_BIT_SCL_RISE;
                } else if (!all_stable) {
                    self.state = .IDLE;
                }
            },
            .WAIT_BIT_SCL_RISE => {
                if (scl_oe.stable_high() and scl_o.rising() and sda_oe.stable_high() and sda_o.stable) {
                    self.bits += 1;
                    self.byte = (self.byte << 1) | @boolToInt(sda_o.value);
                    self.state = .WAIT_BIT_SCL_FALL;
                } else if (!scl_oe.stable_high() or !sda_oe.stable_high()) {
                    self.state = .IDLE;
                    std.debug.print("WAIT_BIT_SCL_RISE: scl_oe({}), sda_oe({})\n", .{ scl_oe, sda_oe });
                    return .Error;
                }
            },
            .WAIT_BIT_SCL_FALL => {
                if (scl_oe.stable_high() and scl_o.falling() and sda_oe.stable_high() and sda_o.stable) {
                    if (self.bits == 8) {
                        self.state = .WAIT_ACK_SCL_RISE;
                        return .AckNack;
                    } else {
                        self.state = .WAIT_BIT_SCL_RISE;
                    }
                } else if (scl_oe.stable_high() and scl_o.stable_high() and sda_oe.stable_high() and sda_o.rising()) {
                    if (self.bits == 1 and self.byte == 0) {
                        self.state = .IDLE;
                        return .Fish;
                    } else {
                        self.state = .IDLE;
                        std.debug.print("WAIT_BIT_SCL_FALL: bits({}), byte({})\n", .{ self.bits, self.byte });
                        return .Error;
                    }
                } else if (scl_oe.stable_high() and scl_o.stable_high() and sda_oe.stable_high() and sda_o.falling()) {
                    // repeated start
                    self.state = .START_SDA_LOW;
                    self.bits = 0;
                    self.byte = 0;
                    return .Fish;
                } else if (!all_stable) {
                    self.state = .IDLE;
                    std.debug.print("WAIT_BIT_SCL_FALL: scl_oe({}), scl_o({}), sda_oe({}), sda_o({})\n", .{ scl_oe, scl_o, sda_oe, sda_o });
                    return .Error;
                }
            },
            .WAIT_ACK_SCL_RISE => {
                if (sda_oe.falling()) {
                    // pass
                } else if (scl_oe.stable_high() and scl_o.rising() and sda_oe.stable_low()) {
                    self.state = .WAIT_ACK_SCL_FALL;
                } else if (!all_stable) {
                    self.state = .IDLE;
                    std.debug.print("WAIT_ACK_SCL_RISE: scl_oe({}), scl_o({}), sda_oe({}), sda_o({})\n", .{ scl_oe, scl_o, sda_oe, sda_o });
                    return .Error;
                }
            },
            .WAIT_ACK_SCL_FALL => {
                if (scl_oe.stable_high() and scl_o.falling()) {
                    self.state = .WAIT_BIT_SCL_RISE;
                    self.bits = 0;
                    self.byte = 0;
                    return .ReleaseSda;
                } else if (!(scl_oe.stable and scl_o.stable)) {
                    self.state = .IDLE;
                    std.debug.print("WAIT_ACK_SCL_FALL: scl_oe({}), scl_o({})\n", .{ scl_oe, scl_o });
                    return .Error;
                }
            },
        }

        return .Pass;
    }
};
