const std = @import("std");

const c = @cImport({
    @cInclude("backends/cxxrtl/cxxrtl_capi.h");
    @cInclude("backends/cxxrtl/cxxrtl_vcd_capi.h");
});

extern "c" fn cxxrtl_design_create() c.cxxrtl_toplevel;

const Cxxrtl = @This();

handle: c.cxxrtl_handle,

pub fn init() Cxxrtl {
    return .{
        .handle = c.cxxrtl_create(cxxrtl_design_create()),
    };
}

pub fn get(self: Cxxrtl, comptime T: type, name: [:0]const u8) Object(T) {
    return self.find(T, name) orelse std.debug.panic("object not found: {s}", .{name});
}

pub fn find(self: Cxxrtl, comptime T: type, name: [:0]const u8) ?Object(T) {
    if (c.cxxrtl_get(self.handle, name)) |handle| {
        return Object(T){ .object = handle };
    } else {
        return null;
    }
}

pub fn step(self: Cxxrtl) void {
    _ = c.cxxrtl_step(self.handle);
}

pub fn deinit(self: Cxxrtl) void {
    c.cxxrtl_destroy(self.handle);
}

pub fn Object(comptime T: type) type {
    return struct {
        const Self = @This();

        object: *c.cxxrtl_object,

        pub fn curr(self: Self) T {
            if (T == bool) {
                return self.object.*.curr[0] == 1;
            } else {
                return @as(T, @intCast(self.object.*.curr[0]));
            }
        }

        pub fn next(self: Self, value: T) void {
            if (T == bool) {
                self.object.*.next[0] = @as(u32, @intFromBool(value));
            } else {
                self.object.*.next[0] = @as(u32, value);
            }
        }
    };
}

pub const Vcd = struct {
    handle: c.cxxrtl_vcd,
    time: u64,

    pub fn init(cxxrtl: Cxxrtl) Vcd {
        const handle = c.cxxrtl_vcd_create();
        c.cxxrtl_vcd_add_from(handle, cxxrtl.handle);
        return .{
            .handle = handle,
            .time = 0,
        };
    }

    pub fn deinit(self: *Vcd) void {
        c.cxxrtl_vcd_destroy(self.handle);
    }

    pub fn sample(self: *Vcd) void {
        self.time += 1;
        c.cxxrtl_vcd_sample(self.handle, self.time);
    }

    pub fn read(self: *Vcd, allocator: std.mem.Allocator) ![]u8 {
        var data: [*c]const u8 = undefined;
        var size: usize = undefined;

        var buffer = std.ArrayList(u8).init(allocator);
        errdefer buffer.deinit();

        while (true) {
            c.cxxrtl_vcd_read(self.handle, &data, &size);
            if (size == 0) {
                break;
            }

            try buffer.appendSlice(data[0..size]);
        }

        return try buffer.toOwnedSlice();
    }
};
