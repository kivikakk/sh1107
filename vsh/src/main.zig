const std = @import("std");
const gk = @import("gamekit");

const DisplayBase = @import("./DisplayBase.zig");
const Display = @import("./Display.zig");
const Cxxrtl = @import("./Cxxrtl.zig");

var display: Display = undefined;

pub fn main() !void {
    try gk.run(.{
        .init = gkInit,
        .update = gkUpdate,
        .render = gkRender,
        .shutdown = gkShutdown,
        .window = .{
            .title = "SH1107 OLED I²C",
            .width = DisplayBase.window_width,
            .height = DisplayBase.window_height,
            .resizable = false,
        },
    });
}

fn gkInit() !void {
    display = try Display.init();
}

fn gkUpdate() !void {
    display.update();
}

fn gkRender() !void {
    display.render();
}

fn gkShutdown() !void {
    display.deinit();
}
