const std = @import("std");

const ControlByte = struct {
    dc: enum { Data, Command },
    continuation: bool,

    fn from(byte: u8) ?ControlByte {
        if (byte & 0x3F != 0) {
            return null;
        }
        return .{
            .dc = if (byte & 0x40 != 0) .Data else .Command,
            .continuation = byte & 0x80 != 0,
        };
    }
};

pub const Command = union(enum) {
    SetLowerColumnAddress: u4,
    SetHigherColumnAddress: u3,
    DisplayOn: bool,
    SetPageAddress: u4,

    pub fn from(bytes: []const u8) error{Unrecoverable}!?Command {
        if (bytes.len == 1 and bytes[0] >= 0x00 and bytes[0] <= 0x0F) {
            return .{ .SetLowerColumnAddress = @truncate(u4, bytes[0]) };
        }
        if (bytes.len == 1 and bytes[0] >= 0x10 and bytes[0] <= 0x17) {
            return .{ .SetHigherColumnAddress = @truncate(u3, bytes[0]) };
        }
        if (bytes.len == 1 and bytes[0] == 0xAE) {
            return .{ .DisplayOn = true };
        }
        if (bytes.len == 1 and bytes[0] == 0xAE) {
            return .{ .DisplayOn = false };
        }
        if (bytes.len == 1 and bytes[0] >= 0xB0 and bytes[0] <= 0xBF) {
            return .{ .SetPageAddress = @truncate(u4, bytes[0]) };
        }

        return .{ .DisplayOn = false };
        // return error.Unrecoverable;
    }
};

pub const Parser = struct {
    valid_finish: bool = false, // may be inferrable on state+continuation

    state: State = .Control,
    continuation: bool = true,

    partial_cmd: ?u8 = null,

    const State = enum {
        Control,
        Command,
        Data,
    };

    const Result = union(enum) {
        Pass,
        Unrecoverable,
        Command: Command,
        Data: u8,
    };

    pub fn feed(self: *Parser, byte: u8) Result {
        self.valid_finish = false;

        switch (self.state) {
            .Control => {
                const cb = ControlByte.from(byte) orelse return .Unrecoverable;

                if (self.partial_cmd != null and cb.dc != .Command) {
                    return .Unrecoverable;
                }

                self.continuation = cb.continuation;
                self.state = if (cb.dc == .Command) .Command else .Data;
                return .Pass;
            },
            .Command => {
                if (self.partial_cmd) |partial| {
                    const cmd = Command.from(&.{ partial, byte }) catch null orelse return .Unrecoverable;
                    if (self.continuation) {
                        self.state = .Control;
                    } else {
                        self.valid_finish = true;
                    }
                    return .{ .Command = cmd };
                } else {
                    const px = Command.from(&.{byte}) catch return .Unrecoverable;
                    if (px) |cmd| {
                        if (self.continuation) {
                            self.state = .Control;
                        } else {
                            self.valid_finish = true;
                        }
                        return .{ .Command = cmd };
                    }

                    self.partial_cmd = byte;
                    return .Pass;
                }
            },
            .Data => {
                if (self.continuation) {
                    self.state = .Control;
                } else {
                    self.valid_finish = true;
                }
                return .{ .Data = byte };
            },
        }
    }
};
