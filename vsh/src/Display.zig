const std = @import("std");
const gk = @import("gamekit");

const DisplayBase = @import("./DisplayBase.zig");
const FPGAThread = @import("./FPGAThread.zig");
const SH1107 = @import("./SH1107.zig");

const Display = @This();

fpga_thread: *FPGAThread,
base: DisplayBase,
img: gk.gfx.Texture,

pub fn init() !Display {
    const fpga_thread = try FPGAThread.start();
    const base = try DisplayBase.init();
    const img = gk.gfx.Texture.init(DisplayBase.i2c_width, DisplayBase.i2c_height);

    return .{
        .fpga_thread = fpga_thread,
        .base = base,
        .img = img,
    };
}

pub fn deinit(self: Display) void {
    self.fpga_thread.stop();
}

pub fn update(self: *Display) bool {
    if (gk.input.keyPressed(.escape)) {
        return false;
    }

    if (gk.input.keyPressed(.key_return)) {
        self.fpga_thread.press_switch_connector();
    }

    return true;
}

pub fn render(self: *Display) void {
    const gfx = gk.gfx;

    gfx.beginPass(.{ .color = gk.math.Color.black });

    gfx.draw.tex(self.base.voyager2, .{ .x = 0, .y = 0 });

    const sh1107 = self.fpga_thread.acquire_sh1107();
    self.drawTop(&sh1107);
    self.drawOLED(&sh1107);

    gfx.endPass();
}

const TopDrawState = struct {
    display: *Display,

    left: f32,
    top: f32,

    pub fn start(display: *Display) TopDrawState {
        return .{
            .display = display,
            .left = @intToFloat(f32, DisplayBase.padding),
            .top = @intToFloat(f32, DisplayBase.padding),
        };
    }

    pub fn check(self: *TopDrawState, name: []const u8, value: bool) void {
        gk.gfx.draw.textOptions(name, self.display.base.fontbook, .{
            .x = self.left + @intToFloat(f32, DisplayBase.checkbox_size + DisplayBase.checkbox_text_gap),
            .y = self.top,
            .alignment = .left_middle,
            .color = DisplayBase.white,
        });
        if (value) {
            // "bold"
            gk.gfx.draw.textOptions(name, self.display.base.fontbook, .{
                .x = self.left + @intToFloat(f32, DisplayBase.checkbox_size + DisplayBase.checkbox_text_gap) + 0.5,
                .y = self.top,
                .alignment = .left_middle,
                .color = DisplayBase.white,
            });
        }

        const y = self.top - @intToFloat(f32, DisplayBase.checkbox_up);

        if (value) {
            gk.gfx.draw.rect(
                .{
                    .x = self.left,
                    .y = y,
                },
                DisplayBase.checkbox_size,
                DisplayBase.checkbox_size,
                DisplayBase.white,
            );
            gk.gfx.draw.hollowRect(
                .{
                    .x = self.left,
                    .y = y,
                },
                DisplayBase.checkbox_size,
                DisplayBase.checkbox_size,
                1,
                DisplayBase.on_border,
            );
        } else {
            gk.gfx.draw.rect(
                .{
                    .x = self.left,
                    .y = y,
                },
                DisplayBase.checkbox_size,
                DisplayBase.checkbox_size,
                DisplayBase.off,
            );
            gk.gfx.draw.hollowRect(
                .{
                    .x = self.left,
                    .y = y,
                },
                DisplayBase.checkbox_size,
                DisplayBase.checkbox_size,
                1,
                DisplayBase.off_border,
            );
        }

        self.top += @intToFloat(f32, DisplayBase.top_row_height);
    }

    pub fn fmt(self: *TopDrawState, name: []const u8, comptime f: []const u8, args: anytype) void {
        var buf1: [64]u8 = undefined;
        var buf2: [64]u8 = undefined;
        const s1 = std.fmt.bufPrint(&buf1, f, args) catch unreachable;
        const s2 = std.fmt.bufPrint(&buf2, "{s}: {s}", .{ name, s1 }) catch unreachable;
        gk.gfx.draw.textOptions(s2, self.display.base.fontbook, .{
            .x = self.left,
            .y = self.top,
            .alignment = .left_middle,
            .color = DisplayBase.white,
        });
        self.top += @intToFloat(f32, DisplayBase.top_row_height);
    }

    pub fn row(self: *TopDrawState) void {
        self.left += @intToFloat(f32, DisplayBase.top_col_width);
        self.top = @intToFloat(f32, DisplayBase.padding);
    }
};

fn drawTop(self: *Display, sh1107: *const SH1107) void {
    var tds = TopDrawState.start(self);
    tds.check("power on", sh1107.power);
    tds.check("dc/dc on", sh1107.dcdc);
    tds.fmt("dclk", "{d}% {d}x", .{ @enumToInt(sh1107.dclk_freq), sh1107.dclk_ratio });
    tds.fmt("pre/dis", "{d}/{d}", .{ sh1107.precharge_period, sh1107.discharge_period });
    tds.fmt("vcom desel", "{x:0>2}", .{sh1107.vcom_desel});

    tds.row();
    tds.check("all on", sh1107.all_on);
    tds.check("reversed", sh1107.reversed);
    tds.fmt("contrast", "{x:0>2}", .{sh1107.contrast});

    tds.row();
    tds.fmt("start", "{x:0>2}/{x:0>2}", .{ sh1107.start_line, sh1107.start_column });
    tds.fmt("address", "{x:0>2}/{x:0>2}", .{ sh1107.page_address, sh1107.column_address });
    tds.fmt("mode", "{s}", .{sh1107.addressing_mode.str()});
    tds.fmt("multiplex", "{x:0>2}", .{sh1107.multiplex});

    tds.row();
    tds.check("seg remap", sh1107.segment_remap == .Flipped);
    tds.check("com rev", sh1107.com_scan_dir == .Backwards);
}

fn dtStart(self: *Display) void {
    self.base.dtStart();
}

fn drawOLED(self: *Display, sh1107: *const SH1107) void {
    if (self.fpga_thread.idata_stale.compareAndSwap(true, false, .Acquire, .Monotonic) == null) {
        self.fpga_thread.idata_mutex.lock();
        defer self.fpga_thread.idata_mutex.unlock();
        self.img.setData(gk.math.Color, &self.fpga_thread.idata);
    }

    if (sh1107.power) {
        gk.gfx.draw.hollowRect(
            .{
                .x = @intToFloat(f32, DisplayBase.padding),
                .y = @intToFloat(f32, DisplayBase.padding + DisplayBase.top_area),
            },
            DisplayBase.border_fill_width,
            DisplayBase.border_fill_height,
            DisplayBase.border_width,
            DisplayBase.on_border,
        );

        gk.gfx.draw.texScaleXY(
            self.img,
            .{
                .x = @intToFloat(f32, DisplayBase.padding + DisplayBase.border_width + if (sh1107.com_scan_dir == .Backwards) DisplayBase.i2c_width * DisplayBase.display_scale else 0),
                .y = @intToFloat(f32, DisplayBase.padding + DisplayBase.border_width + DisplayBase.top_area),
            },
            @intToFloat(f32, DisplayBase.display_scale) * if (sh1107.com_scan_dir == .Backwards) @as(f32, -1) else @as(f32, 1),
            DisplayBase.display_scale,
        );
    } else {
        gk.gfx.draw.rect(
            .{
                .x = @intToFloat(f32, DisplayBase.padding),
                .y = @intToFloat(f32, DisplayBase.padding + DisplayBase.top_area),
            },
            DisplayBase.border_fill_width,
            DisplayBase.border_fill_height,
            DisplayBase.off,
        );
        gk.gfx.draw.hollowRect(
            .{
                .x = @intToFloat(f32, DisplayBase.padding),
                .y = @intToFloat(f32, DisplayBase.padding + DisplayBase.top_area),
            },
            DisplayBase.border_fill_width,
            DisplayBase.border_fill_height,
            DisplayBase.border_width,
            DisplayBase.off_border,
        );
    }
}
