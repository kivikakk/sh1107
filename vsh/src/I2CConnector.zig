const std = @import("std");

const Cxxrtl = @import("./Cxxrtl.zig");
const Tick = @import("./OLEDConnector.zig").Tick;
const RW = @import("./OLEDConnector.zig").RW;
const Sample = @import("./Sample.zig").Sample;

addr: u7,

byte_transmitter: ByteTransmitter = .{},
addressed: bool = false,

scl_o: Sample(bool),
scl_oe: Sample(bool),
sda_o: Sample(bool),
sda_oe: Sample(bool),
sda_i: Cxxrtl.Object(bool),

pub fn init(cxxrtl: Cxxrtl, addr: u7) @This() {
    const scl_o = Sample(bool).init(cxxrtl, "scl__o", false);
    const scl_oe = Sample(bool).init(cxxrtl, "scl__oe", false);
    const sda_o = Sample(bool).init(cxxrtl, "sda__o", false);
    const sda_oe = Sample(bool).init(cxxrtl, "sda__oe", false);
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

pub fn tick(self: *@This()) Tick {
    const scl_o = self.scl_o.tick();
    const scl_oe = self.scl_oe.tick();
    const sda_o = self.sda_o.tick();
    const sda_oe = self.sda_oe.tick();

    const result = self.byte_transmitter.process(scl_o, scl_oe, sda_o, sda_oe);
    switch (result) {
        .Pass => return .Pass,
        .WriteAck => {
            const byte = self.byte_transmitter.byte;
            // XXX(Ch): This is probably buggy: if we get a START for not-us, we
            // .Pass, but then imagine the first data byte looks like it
            // addressses us.
            if (!self.addressed) {
                const addr: u7 = @truncate(u7, byte >> 1);
                const rw = @intToEnum(RW, @truncate(u1, byte));
                if (addr == self.addr and rw == .W) {
                    self.sda_i.next(false);
                    self.addressed = true;
                    self.byte_transmitter.rw = .W;
                    return .AddressedWrite;
                } else if (addr == self.addr and rw == .R) {
                    self.sda_i.next(false);
                    self.addressed = true;
                    self.byte_transmitter.rw = .W;
                    self.byte_transmitter.next_rw = .R;
                    return .{ .AddressedRead = &self.byte_transmitter.byte };
                } else {
                    return .Pass;
                }
            } else {
                self.sda_i.next(false);
                return .{ .Byte = byte };
            }
        },
        .ReadAck => {
            return .{ .AddressedRead = &self.byte_transmitter.byte };
        },
        .SetSda => |v| {
            self.sda_i.next(v);
            return .Pass;
        },
        .Error => {
            self.sda_i.next(true);
            std.debug.print("got error, resetting\n", .{});
            self.addressed = false;
            self.byte_transmitter.rw = .W;
            return .Error;
        },
        .Fish => {
            self.sda_i.next(true);
            if (!self.addressed) {
                std.debug.print("command parser fish while unaddressed\n", .{});
            }
            self.addressed = false;
            self.byte_transmitter.rw = .W;
            return .Fish;
        },
    }
}

pub fn reset(self: *@This()) void {
    self.addressed = false;
}

const ByteTransmitter = struct {
    rw: RW = .W,
    next_rw: RW = .W,
    state: enum {
        IDLE,
        START_SDA_LOW,
        WAIT_BIT_SCL_RISE,
        WAIT_BIT_SCL_FALL,
        WAIT_ACK_SCL_RISE,
        WAIT_ACK_SCL_FALL,
    } = .IDLE,
    bits: u3 = 0,
    byte: u8 = 0,

    const Result = union(enum) {
        Pass,
        WriteAck,
        ReadAck,
        SetSda: bool,
        Error,
        Fish,
    };

    fn process(self: *ByteTransmitter, scl_o: *const Sample(bool), scl_oe: *const Sample(bool), sda_o: *const Sample(bool), sda_oe: *const Sample(bool)) Result {
        const all_stable = scl_oe.stable() and scl_o.stable() and sda_oe.stable() and sda_o.stable();

        switch (self.state) {
            .IDLE => {
                if (scl_oe.stable_high() and scl_o.stable_high() and sda_oe.stable_high() and sda_o.falling()) {
                    self.state = .START_SDA_LOW;
                    self.bits = 0;
                    self.byte = 0;
                    return .{ .SetSda = true };
                }
                return .Pass;
            },
            .START_SDA_LOW => {
                if (scl_oe.stable_high() and scl_o.falling() and sda_oe.stable_high() and sda_o.stable_low()) {
                    self.state = .WAIT_BIT_SCL_RISE;
                } else if (!all_stable) {
                    self.state = .IDLE;
                }
                return .Pass;
            },
            .WAIT_BIT_SCL_RISE => {
                if (self.rw == .W) {
                    if (scl_oe.stable_high() and scl_o.rising() and sda_oe.stable_high() and sda_o.stable()) {
                        self.byte = (self.byte << 1) | @boolToInt(sda_o.curr);
                        self.state = .WAIT_BIT_SCL_FALL;
                        return .Pass;
                    } else if (!scl_oe.stable_high() or !sda_oe.stable_high()) {
                        self.state = .IDLE;
                        std.debug.print("WAIT_BIT_SCL_RISE(W): scl_oe({}), sda_oe({})\n", .{ scl_oe, sda_oe });
                        return .Error;
                    }
                } else {
                    if (scl_oe.stable_high() and scl_o.rising() and sda_oe.stable_low()) {
                        self.state = .WAIT_BIT_SCL_FALL;
                        return .Pass;
                    } else if (!scl_oe.stable_high() or !sda_oe.stable_low()) {
                        self.state = .IDLE;
                        std.debug.print("WAIT_BIT_SCL_RISE(R): scl_oe({}), sda_oe({})\n", .{ scl_oe, sda_oe });
                        return .Error;
                    }
                }
                return .Pass;
            },
            .WAIT_BIT_SCL_FALL => {
                if (self.rw == .W) {
                    if (scl_oe.stable_high() and scl_o.falling() and sda_oe.falling() and sda_o.stable()) {
                        if (self.bits != 7) {
                            self.state = .IDLE;
                            std.debug.print("WAIT_BIT_SCL_FALL(W): bits({}), byte({}) -- scl_oe({}), scl_o({}), sda_oe({}), sda_o({})\n", .{ self.bits, self.byte, scl_oe, scl_o, sda_oe, sda_o });
                            return .Error;
                        }
                        self.state = .WAIT_ACK_SCL_RISE;
                        return .WriteAck;
                    } else if (scl_oe.stable_high() and scl_o.falling() and sda_oe.stable_high() and sda_o.stable()) {
                        if (self.bits == 7) {
                            self.state = .IDLE;
                            std.debug.print("WAIT_BIT_SCL_FALL(W): bits({}), byte({}) -- scl_oe({}), scl_o({}), sda_oe({}), sda_o({})\n", .{ self.bits, self.byte, scl_oe, scl_o, sda_oe, sda_o });
                            return .Error;
                        }
                        self.bits += 1;
                        self.state = .WAIT_BIT_SCL_RISE;
                        return .Pass;
                    } else if (scl_oe.stable_high() and scl_o.stable_high() and sda_oe.stable_high() and sda_o.rising()) {
                        if (self.bits == 0 and self.byte == 0) {
                            self.state = .IDLE;
                            return .Fish;
                        } else {
                            self.state = .IDLE;
                            std.debug.print("WAIT_BIT_SCL_FALL(W): bits({}), byte({})\n", .{ self.bits, self.byte });
                            return .Error;
                        }
                    } else if (scl_oe.stable_high() and scl_o.stable_high() and sda_oe.stable_high() and sda_o.falling()) {
                        // repeated start
                        self.state = .START_SDA_LOW;
                        self.rw = .W;
                        self.bits = 0;
                        self.byte = 0;
                        return .Fish;
                    } else if (!all_stable) {
                        self.state = .IDLE;
                        std.debug.print("WAIT_BIT_SCL_FALL(W): scl_oe({}), scl_o({}), sda_oe({}), sda_o({})\n", .{ scl_oe, scl_o, sda_oe, sda_o });
                        return .Error;
                    }
                    return .Pass;
                } else {
                    if (scl_oe.stable_high() and scl_o.falling() and sda_oe.stable_low()) {
                        if (self.bits == 7) {
                            self.state = .WAIT_ACK_SCL_RISE;
                            return .Pass;
                        } else {
                            self.bits += 1;
                            self.state = .WAIT_BIT_SCL_RISE;
                            return self.prepareSendBit();
                        }
                    } else if (!all_stable) {
                        self.state = .IDLE;
                        std.debug.print("WAIT_BIT_SCL_FALL(R): bits({}), byte({}) -- scl_oe({}), scl_o({}), sda_oe({}), sda_o({})\n", .{ self.bits, self.byte, scl_oe, scl_o, sda_oe, sda_o });
                        return .Error;
                    }
                    return .Pass;
                }
            },
            .WAIT_ACK_SCL_RISE => {
                if (self.rw == .W) {
                    if (sda_oe.falling()) {
                        return .Pass;
                    } else if (scl_oe.stable_high() and scl_o.rising() and sda_oe.stable_low()) {
                        self.state = .WAIT_ACK_SCL_FALL;
                        return .Pass;
                    } else if (!all_stable) {
                        self.state = .IDLE;
                        std.debug.print("WAIT_ACK_SCL_RISE(W): scl_oe({}), scl_o({}), sda_oe({}), sda_o({})\n", .{ scl_oe, scl_o, sda_oe, sda_o });
                        return .Error;
                    }
                    return .Pass;
                } else {
                    if (sda_oe.rising()) {
                        return .Pass;
                    } else if (scl_oe.stable_high() and scl_o.rising() and sda_oe.stable_high()) {
                        self.state = .WAIT_ACK_SCL_FALL;
                        const ack = !sda_o.curr;
                        if (ack) {
                            return .ReadAck;
                        } else {
                            self.next_rw = .W;
                            return .Pass;
                        }
                    } else if (!all_stable) {
                        self.state = .IDLE;
                        std.debug.print("WAIT_ACK_SCL_RISE(R): scl_oe({}), scl_o({}), sda_oe({}), sda_o({})\n", .{ scl_oe, scl_o, sda_oe, sda_o });
                        return .Error;
                    }
                    return .Pass;
                }
            },
            .WAIT_ACK_SCL_FALL => {
                if (scl_oe.stable_high() and scl_o.falling()) {
                    self.state = .WAIT_BIT_SCL_RISE;
                    self.bits = 0;
                    self.rw = self.next_rw;
                    if (self.rw == .W) {
                        self.byte = 0;
                        return .{ .SetSda = true };
                    } else {
                        return self.prepareSendBit();
                    }
                } else if (!(scl_oe.stable() and scl_o.stable())) {
                    self.state = .IDLE;
                    std.debug.print("WAIT_ACK_SCL_FALL: scl_oe({}), scl_o({})\n", .{ scl_oe, scl_o });
                    return .Error;
                }
                return .Pass;
            },
        }
    }

    fn prepareSendBit(self: *ByteTransmitter) Result {
        return .{ .SetSda = (self.byte >> (7 - self.bits)) & 1 == 1 };
    }
};
