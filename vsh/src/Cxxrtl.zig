const c = @cImport({
    @cInclude("backends/cxxrtl/cxxrtl_capi.h");
});

extern "c" fn cxxrtl_design_create() c.cxxrtl_toplevel;

handle: c.cxxrtl_handle,

pub fn init() @This() {
    return .{
        .handle = c.cxxrtl_create(cxxrtl_design_create()),
    };
}

pub fn get(self: @This(), comptime T: type, name: [:0]const u8) Object(T) {
    return self.find(T, name) orelse @panic("object not found");
}

pub fn find(self: @This(), comptime T: type, name: [:0]const u8) ?Object(T) {
    if (c.cxxrtl_get(self.handle, name)) |handle| {
        return Object(T){ .object = handle };
    } else {
        return null;
    }
}

pub fn step(self: @This()) void {
    _ = c.cxxrtl_step(self.handle);
}

pub fn deinit(self: @This()) void {
    c.cxxrtl_destroy(self.handle);
}

pub fn Object(comptime T: type) type {
    return struct {
        const Self = @This();

        object: *c.cxxrtl_object,

        pub fn curr(self: Self) T {
            return @intCast(T, self.object.*.curr[0]);
        }

        pub fn next(self: Self, value: T) void {
            if (T == bool) {
                self.object.*.next[0] = @as(u32, @boolToInt(value));
            } else {
                self.object.*.next[0] = @as(u32, value);
            }
        }
    };
}
