const Cxxrtl = @import("./Cxxrtl.zig");
const I2CConnector = @import("./I2CConnector.zig");
const Display = @import("./Display.zig");

i2c_connector: I2CConnector,

pub fn init(cxxrtl: Cxxrtl, comptime name: []const u8, addr: u7) @This() {
    return .{
        .i2c_connector = I2CConnector.init(cxxrtl, name ++ " i2c", addr),
    };
}

pub fn tick(self: *@This(), display: *Display) void {
    _ = display;
    _ = self;
}
