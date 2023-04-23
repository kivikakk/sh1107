const std = @import("std");

const c = @cImport({
    @cInclude("backends/cxxrtl/cxxrtl_capi.h");
});

extern "c" fn cxxrtl_design_create() c.cxxrtl_toplevel;

pub fn main() !void {
    const handle = c.cxxrtl_create(cxxrtl_design_create());
    defer c.cxxrtl_destroy(handle);

    const clk = c.cxxrtl_get(handle, "clk");
    const swi = c.cxxrtl_get(handle, "switch");
    const last_cmd = c.cxxrtl_get(handle, "o_last_cmd");
    const oled_result = c.cxxrtl_get(handle, "oled o_result");

    _ = c.cxxrtl_step(handle);

    for (0..3000) |i| {
        // i%2==0: clock rises
        // i%2==1: clock falls
        clk.*.next[0] = if (clk.*.curr[0] == 0) 1 else 0;

        // XXX(sar) idk if i should change things with clk rise or fall
        // Clock rise, probably, since things will usually trigger posedge.
        if (i == 0) {
            swi.*.next[0] = 1;
        } else if (i == 2) {
            swi.*.next[0] = 0;
        }

        _ = c.cxxrtl_step(handle);
        std.debug.print("step {}: clk {}, last_cmd {}, oled_result {}\n", .{ i, clk.*.curr[0], last_cmd.*.curr[0], oled_result.*.curr[0] });

        if (oled_result.*.curr[0] == 2) {
            break;
        }
    }
}
