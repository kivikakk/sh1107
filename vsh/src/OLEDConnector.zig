const std = @import("std");

const Cxxrtl = @import("./Cxxrtl.zig");
const I2CConnector = @import("./I2CConnector.zig");
const I2CBBConnector = @import("./I2CBBConnector.zig");
const FPGAThread = @import("./FPGAThread.zig");
const Cmd = @import("./Cmd.zig");

const OLEDConnector = @This();

const InnerI2CConnector = union(enum) {
    I2CConnector: I2CConnector,
    I2CBBConnector: I2CBBConnector,
};

i2c_connector: InnerI2CConnector,

state: union(enum) {
    Unaddressed,
    AddressedWrite: Cmd.Parser,
    AddressedRead,
} = .Unaddressed,

pub const Tick = union(enum) {
    Pass,
    AddressedWrite,
    AddressedRead: *u8,
    Error,
    Fish,
    Byte: u8,
};

pub const RW = enum(u1) {
    W = 0,
    R = 1,
};

pub fn tick(self: *OLEDConnector, fpga_thread: *FPGAThread) void {
    self.tick_i2c(fpga_thread);
}

fn tick_i2c(self: *OLEDConnector, fpga_thread: *FPGAThread) void {
    switch (self.i2c_connector) {
        inline else => |*i2c_connector| {
            switch (i2c_connector.tick()) {
                .Pass => {},
                .AddressedWrite => {
                    self.state = .{ .AddressedWrite = .{} };
                },
                .AddressedRead => |byte_out| {
                    self.state = .AddressedRead;
                    const sh1107 = fpga_thread.acquire_sh1107();

                    // not busy, display on/off, ID=7
                    byte_out.* = 0x07 | (if (sh1107.power) @as(u8, 0x00) else @as(u8, 0x40));
                },
                .Error => {
                    std.debug.print("i2c error\n", .{});
                    self.state = .Unaddressed;
                },
                .Fish => {
                    switch (self.state) {
                        .Unaddressed => std.debug.print("i2c fish while unaddressed\n", .{}),
                        .AddressedWrite => |parser| if (!parser.valid_finish) {
                            std.debug.print("i2c fish without valid_finish\n", .{});
                        },
                        .AddressedRead => {},
                    }
                    self.state = .Unaddressed;
                },
                .Byte => |byte| {
                    switch (self.state) {
                        .AddressedWrite => |*parser| switch (parser.feed(byte)) {
                            .Pass => {},
                            .Unrecoverable => {
                                std.debug.print("command parser noped out, fed {x:0>2} -- " ++
                                    "state: {} / continuation: {} / partial_cmd: {?x:0>2}\n", .{
                                    byte,
                                    parser.state,
                                    parser.continuation,
                                    parser.partial_cmd,
                                });
                                self.state = .Unaddressed;
                                i2c_connector.reset();
                            },
                            .Command => |cmd| {
                                fpga_thread.process_cmd(cmd);
                            },
                            .Data => |data| {
                                fpga_thread.process_data(data);
                            },
                        },
                        else => std.debug.print("i2c got Byte while not AddressedWrite\n", .{}),
                    }
                },
            }
        },
    }
}

pub fn init(cxxrtl: Cxxrtl, addr: u7) OLEDConnector {
    var i2c_connector: InnerI2CConnector = undefined;

    if (cxxrtl.find(bool, "scl__o") != null) {
        i2c_connector = .{ .I2CConnector = I2CConnector.init(cxxrtl, addr) };
    } else {
        i2c_connector = .{ .I2CBBConnector = I2CBBConnector.init(cxxrtl, addr) };
    }

    return .{
        .i2c_connector = i2c_connector,
    };
}
