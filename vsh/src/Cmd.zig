const std = @import("std");

const SH1107 = @import("./SH1107.zig");

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
    SetMemoryAddressingMode: SH1107.AddrMode,
    SetContrastControlRegister: u8,
    SetSegmentRemap: SH1107.SegRemap,
    SetMultiplexRatio: u8,
    SetEntireDisplayOn: bool,
    SetDisplayReverse: bool,
    SetDisplayOffset: u7,
    SetDCDC: bool,
    DisplayOn: bool,
    SetPageAddress: u4,
    SetCommonOutputScanDirection: SH1107.COMScanDir,
    SetDisplayClockFrequency: struct {
        ratio: u5,
        frequency: SH1107.DclkFreq,
    },
    SetPreDischargePeriod: struct {
        precharge: u4,
        discharge: u4,
    },
    SetVCOMDeselectLevel: u8,
    SetDisplayStartColumn: u7,
    ReadModifyWrite,
    End,
    Nop,

    pub fn from(bytes: []const u8) error{Unrecoverable}!?Command {
        std.debug.assert(bytes.len >= 1);
        if (bytes[0] >= 0x00 and bytes[0] <= 0x0F) {
            if (bytes.len == 1) {
                return .{ .SetLowerColumnAddress = @truncate(u4, bytes[0]) };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] >= 0x10 and bytes[0] <= 0x17) {
            if (bytes.len == 1) {
                return .{ .SetHigherColumnAddress = @truncate(u3, bytes[0]) };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0x20) {
            if (bytes.len == 1) {
                return .{ .SetMemoryAddressingMode = .Page };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0x21) {
            if (bytes.len == 1) {
                return .{ .SetMemoryAddressingMode = .Column };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0x81) {
            if (bytes.len == 1) {
                return null;
            }
            if (bytes.len == 2) {
                return .{ .SetContrastControlRegister = bytes[1] };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xA0) {
            if (bytes.len == 1) {
                return .{ .SetSegmentRemap = .Normal };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xA1) {
            if (bytes.len == 1) {
                return .{ .SetSegmentRemap = .Flipped };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xA8) {
            if (bytes.len == 1) {
                return null;
            }
            if (bytes.len == 2) {
                return .{ .SetMultiplexRatio = @as(u8, @truncate(u7, bytes[1])) + 1 };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xA4) {
            if (bytes.len == 1) {
                return .{ .SetEntireDisplayOn = false };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xA5) {
            if (bytes.len == 1) {
                return .{ .SetEntireDisplayOn = true };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xA6) {
            if (bytes.len == 1) {
                return .{ .SetDisplayReverse = false };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xA7) {
            if (bytes.len == 1) {
                return .{ .SetDisplayReverse = true };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xD3) {
            if (bytes.len == 1) {
                return null;
            }
            if (bytes.len == 2) {
                return .{ .SetDisplayOffset = @truncate(u7, bytes[1]) };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xAD) {
            if (bytes.len == 1) {
                return null;
            }
            if (bytes.len == 2) {
                return .{ .SetDCDC = bytes[1] == 0x8B };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xAE) {
            if (bytes.len == 1) {
                return .{ .DisplayOn = false };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xAF) {
            if (bytes.len == 1) {
                return .{ .DisplayOn = true };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] >= 0xB0 and bytes[0] <= 0xBF) {
            if (bytes.len == 1) {
                return .{ .SetPageAddress = @truncate(u4, bytes[0]) };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] >= 0xC0 and bytes[0] <= 0xCF) {
            if (bytes.len == 1) {
                return .{
                    .SetCommonOutputScanDirection = if ((bytes[0] & 8) == 8) .Backwards else .Forwards,
                };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xD5) {
            if (bytes.len == 1) {
                return null;
            }
            if (bytes.len == 2) {
                return .{ .SetDisplayClockFrequency = .{
                    .ratio = @as(u5, @truncate(u4, bytes[1])) + 1,
                    .frequency = @intToEnum(SH1107.DclkFreq, @truncate(u4, bytes[1] >> 4)),
                } };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xD9) {
            if (bytes.len == 1) {
                return null;
            }
            if (bytes.len == 2) {
                return .{ .SetPreDischargePeriod = .{
                    .precharge = @truncate(u4, bytes[1]),
                    .discharge = @truncate(u4, bytes[1] >> 4),
                } };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xDB) {
            if (bytes.len == 1) {
                return null;
            }
            if (bytes.len == 2) {
                return .{ .SetVCOMDeselectLevel = bytes[1] };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xDC) {
            if (bytes.len == 1) {
                return null;
            }
            if (bytes.len == 2) {
                return .{ .SetDisplayStartColumn = @truncate(u7, bytes[1]) };
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xE0) {
            if (bytes.len == 1) {
                return .ReadModifyWrite;
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xEE) {
            if (bytes.len == 1) {
                return .End;
            }
            return error.Unrecoverable;
        }
        if (bytes[0] == 0xE3) {
            if (bytes.len == 1) {
                return .Nop;
            }
            return error.Unrecoverable;
        }
        return error.Unrecoverable;
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

        std.debug.print("{s} ({s}) feed: {x:0>2}\n", .{ switch (self.state) {
            .Control => "Ctrl",
            .Command => "Cmd ",
            .Data => "Data",
        }, switch (self.continuation) {
            true => " C",
            false => "nc",
        }, byte });

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
                    self.partial_cmd = null;
                    return .{ .Command = cmd };
                } else {
                    const px = Command.from(&.{byte}) catch return .Unrecoverable;
                    if (self.continuation) {
                        self.state = .Control;
                    } else {
                        self.valid_finish = true;
                    }
                    if (px) |cmd| {
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
