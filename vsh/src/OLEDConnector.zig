const std = @import("std");

const Cxxrtl = @import("./Cxxrtl.zig");
const I2CConnector = @import("./I2CConnector.zig");
const Display = @import("./Display.zig");
const Cmd = @import("./Cmd.zig");

i2c_connector: I2CConnector,
parser: ?Cmd.Parser = null,

pub fn init(cxxrtl: Cxxrtl, addr: u7) @This() {
    return .{
        .i2c_connector = I2CConnector.init(cxxrtl, addr),
    };
}

pub fn tick(self: *@This(), display: *Display) void {
    switch (self.i2c_connector.tick()) {
        .Pass => {},
        .Addressed => {
            self.parser = .{};
        },
        .Error => {
            self.parser = null;
        },
        .Fish => {
            if (self.parser == null or !self.parser.?.valid_finish) {
                std.debug.print("command parser fish without valid_finish\n", .{});
            }
            self.parser = null;
        },
        .Byte => |byte| switch (self.parser.?.feed(byte)) {
            .Pass => {
                std.debug.print("pass {x:0>2}\n", .{byte});
            },
            .Unrecoverable => {
                std.debug.print("command parser noped out, fed {x:0>2} -- " ++
                    "state: {} / continuation: {} / partial_cmd: {?x:0>2}\n", .{
                    byte,
                    self.parser.?.state,
                    self.parser.?.continuation,
                    self.parser.?.partial_cmd,
                });
                self.parser = null;
                self.i2c_connector.reset();
            },
            .Command => |cmd| {
                std.debug.print("cmd {x:0>2}\n", .{byte});
                display.process_cmd(cmd);
            },
            .Data => |data| {
                display.process_data(data);
            },
        },
    }
}
