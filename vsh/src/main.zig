const std = @import("std");
const gk = @import("gamekit");

const DisplayBase = @import("./DisplayBase.zig");
const Display = @import("./Display.zig");
const Cxxrtl = @import("./Cxxrtl.zig");

var display: Display = undefined;
pub var write_vcd: bool = false;

export const spi_flash_content = @embedFile("rom.bin");
export const spi_flash_base: u32 = 0x800000;
export const spi_flash_length: u32 = spi_flash_content.len;

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();

    var allocator = gpa.allocator();

    {
        var args = try std.process.argsWithAllocator(allocator);
        defer args.deinit();

        // skip argv[0]
        _ = args.next();

        while (args.next()) |arg| {
            if (std.mem.eql(u8, arg, "-v") or std.mem.eql(u8, arg, "--vcd")) {
                write_vcd = true;
            } else {
                std.debug.print("ARG: {s}\n", .{arg});
                @panic("unknown arg encountered");
            }
        }
    }

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

fn gkUpdate() !bool {
    return display.update();
}

fn gkRender() !void {
    display.render();
}

fn gkShutdown() !void {
    display.deinit();
}
