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

pub fn get(self: @This(), name: [:0]const u8) *c.cxxrtl_object {
    return c.cxxrtl_get(self.handle, name);
}

pub fn step(self: @This()) void {
    _ = c.cxxrtl_step(self.handle);
}

pub fn deinit(self: @This()) void {
    c.cxxrtl_destroy(self.handle);
}
