const std = @import("std");

const Cxxrtl = @import("./Cxxrtl.zig");

pub fn Sample(comptime T: type) type {
    return struct {
        const Self = @This();

        object: Cxxrtl.Object(T),
        prev: T,
        curr: T,

        pub fn init(cxxrtl: Cxxrtl, name: [:0]const u8, start: T) Self {
            return .{
                .object = cxxrtl.get(T, name),
                .prev = start,
                .curr = start,
            };
        }

        pub fn tick(self: *Self) *Self {
            self.prev = self.curr;
            self.curr = self.object.curr();
            return self;
        }

        pub inline fn stable(self: Self) bool {
            return self.curr == self.prev;
        }

        pub fn format(self: Self, comptime fmt: []const u8, options: std.fmt.FormatOptions, writer: anytype) !void {
            _ = options;
            _ = fmt;
            if (self.prev != self.curr) {
                return std.fmt.format(writer, "{} -> {}", .{ self.prev, self.curr });
            } else {
                return std.fmt.format(writer, "{}", .{self.curr});
            }
        }

        pub usingnamespace if (T == bool) struct {
            pub inline fn stable_high(self: Self) bool {
                return self.prev and self.curr;
            }

            pub inline fn stable_low(self: Self) bool {
                return !self.prev and !self.curr;
            }

            pub inline fn falling(self: Self) bool {
                return self.prev and !self.curr;
            }

            pub inline fn rising(self: Self) bool {
                return !self.prev and self.curr;
            }
        } else struct {};
    };
}
