const Cxxrtl = @import("./Cxxrtl.zig");

addr: u7,

byte_receiver: ByteReceiver = .{},
addressed: bool = false,

pub fn init(cxxrtl: Cxxrtl, comptime name: []const u8, addr: u7) @This() {
    _ = cxxrtl.get(bool, name ++ " scl o");
    _ = cxxrtl.get(bool, name ++ " scl oe");
    _ = cxxrtl.get(bool, name ++ " sda o");
    _ = cxxrtl.get(bool, name ++ " sda oe");
    _ = cxxrtl.get(bool, name ++ " sda i");

    return .{
        .addr = addr,
    };
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
    bits: u3 = 0,
    byte: u8 = 0,
};
