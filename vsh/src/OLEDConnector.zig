const std = @import("std");

const Cxxrtl = @import("./Cxxrtl.zig");
const I2CConnector = @import("./I2CConnector.zig");
const FPGAThread = @import("./FPGAThread.zig");
const Cmd = @import("./Cmd.zig");

i2c_connector: I2CConnector,
parser: ?Cmd.Parser = null,

pub fn init(cxxrtl: Cxxrtl, addr: u7) @This() {
    return .{
        .i2c_connector = I2CConnector.init(cxxrtl, addr),
    };
}

pub fn tick(self: *@This(), fpga_thread: *FPGAThread) void {
    switch (self.i2c_connector.tick()) {
        .Pass => {},
        .Addressed => {
            std.debug.print("addressed\n", .{});
            self.parser = .{};
        },
        .Error => {
            std.debug.print("i2c error\n", .{});
            self.parser = null;
        },
        .Fish => {
            if (self.parser == null) {
                std.debug.print("i2c fish without parser\n", .{});
            } else if (!self.parser.?.valid_finish) {
                std.debug.print("i2c fish without valid_finish\n", .{});
            }
            self.parser = null;
        },
        .Byte => |byte| switch (self.parser.?.feed(byte)) {
            .Pass => {},
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
                fpga_thread.process_cmd(cmd);
            },
            .Data => |data| {
                fpga_thread.process_data(data);
            },
        },
    }
}
