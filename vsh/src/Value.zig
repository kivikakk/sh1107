const std = @import("std");

pub fn Value(comptime T: type) type {
    return struct {
        const Self = @This();

        value: T,
        prev: T,

        pub inline fn stable(self: Self) bool {
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

        pub usingnamespace if (T == bool) struct {
            pub inline fn stable_high(self: Self) bool {
                return self.prev and self.value;
            }

            pub inline fn stable_low(self: Self) bool {
                return !self.prev and !self.value;
            }

            pub inline fn falling(self: Self) bool {
                return self.prev and !self.value;
            }

            pub inline fn rising(self: Self) bool {
                return !self.prev and self.value;
            }
        } else struct {};
    };
}

pub fn track(target: anytype, comptime T: type, comptime field: []const u8) Value(T) {
    const value = @field(target, field).curr();
    defer @field(target, field ++ "_prev") = value;

    const prev = @field(target, field ++ "_prev");

    return .{ .value = value, .prev = prev };
}
