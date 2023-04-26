const std = @import("std");
const gk = @import("gamekit");
const Color = gk.math.Color;

voyager2: gk.gfx.Texture,
fontbook: *gk.gfx.FontBook,

pub const i2c_width: u16 = 128;
pub const i2c_height: u16 = 128;
pub const display_scale: u16 = 4;

pub const border_width: u16 = 4;
pub const padding: u16 = 10;

pub const top_area: u16 = 112;
pub const checkbox_size: u16 = 10;
pub const checkbox_text_gap: u16 = 6;
pub const checkbox_across: u16 = 80;
pub const checkbox_down: u16 = 6;

pub const top_col_width: u16 = 142;
pub const top_row_height: u16 = 16;

////

const border_alpha: u8 = 240;
const alpha: u8 = 200;
pub const off: Color = .{ .comps = .{ .r = 0, .g = 10, .b = 50, .a = alpha } };
pub const off_border: Color = .{ .comps = .{ .r = 64, .g = 64, .b = 64, .a = border_alpha } };
pub const on_border: Color = .{ .comps = .{ .r = 192, .g = 192, .b = 192, .a = border_alpha } };

pub const black: Color = .{ .comps = .{ .r = 0, .g = 10, .b = 100, .a = alpha } };
pub const white: Color = .{ .comps = .{ .r = 255, .g = 255, .b = 255, .a = alpha } };

////

pub const window_width = i2c_width * display_scale + 2 * padding + 2 * border_width;
pub const window_height = i2c_height * display_scale + 2 * padding + 2 * border_width + top_area;

pub const border_fill_width = i2c_width * display_scale + 2 * border_width;
pub const border_fill_height = i2c_height * display_scale + 2 * border_width;

////

pub fn init() !@This() {
    const voyager2 = try gk.gfx.Texture.initFromFile(std.heap.c_allocator, "voyager2.jpg", .linear);
    const fontbook = try gk.gfx.FontBook.init(std.heap.c_allocator, 128, 128, .nearest);
    _ = fontbook.addFont("ibm3161-7f.ttf");
    fontbook.setSize(16);

    return .{
        .voyager2 = voyager2,
        .fontbook = fontbook,
    };
}
