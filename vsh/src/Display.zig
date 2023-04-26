const std = @import("std");
const gk = @import("gamekit");

const DisplayBase = @import("./DisplayBase.zig");
const Cxxrtl = @import("./Cxxrtl.zig");
const SH1107 = @import("./SH1107.zig");
const Cmd = @import("./Cmd.zig");

const SwitchConnector = @import("./SwitchConnector.zig");
const OLEDConnector = @import("./OLEDConnector.zig");

const Display = @This();

base: DisplayBase,
cxxrtl: Cxxrtl,
sh1107: SH1107,

switch_connector: ?SwitchConnector,
oled_connector: OLEDConnector,

idata: [DisplayBase.i2c_width * DisplayBase.i2c_height]gk.math.Color = [_]gk.math.Color{DisplayBase.black} ** (DisplayBase.i2c_width * DisplayBase.i2c_height),
img: gk.gfx.Texture,
img_stale: bool = true,

pub fn init() !Display {
    const base = try DisplayBase.init();
    const cxxrtl = Cxxrtl.init();

    const img = gk.gfx.Texture.init(DisplayBase.i2c_width, DisplayBase.i2c_height);

    var switch_connector: ?SwitchConnector = null;
    if (cxxrtl.find(bool, "switch")) |swi| {
        switch_connector = SwitchConnector.init(swi);
    }

    const oled_connector = OLEDConnector.init(cxxrtl, 0x3c);

    return .{
        .base = base,
        .cxxrtl = cxxrtl,
        .sh1107 = .{},

        .switch_connector = switch_connector,
        .oled_connector = oled_connector,

        .img = img,
    };
}

pub fn deinit(self: Display) void {
    self.cxxrtl.deinit();
}

var last_oled_result: u2 = 0;

pub fn update(self: *Display) bool {
    if (gk.input.keyPressed(.escape)) {
        return false;
    }

    if (gk.input.keyPressed(.key_return)) {
        self.switch_connector.?.press();
    }

    const clk = self.cxxrtl.get(bool, "clk");
    const last_cmd = self.cxxrtl.get(u8, "o_last_cmd");
    _ = last_cmd;
    const oled_result = self.cxxrtl.get(u2, "oled o_result");

    // TODO: put in own thread?
    // could be faster ...
    for (0..4000) |_| {
        clk.next(true);
        if (self.switch_connector) |*swicon| {
            swicon.tick();
        }
        self.oled_connector.tick(self);
        self.cxxrtl.step();

        clk.next(false);
        self.cxxrtl.step();

        const curr_oled_result = oled_result.curr();
        if (curr_oled_result != last_oled_result) {
            std.debug.print("oled_result -> {d}\n", .{curr_oled_result});
            last_oled_result = curr_oled_result;
        }
    }

    return true;
}

pub fn render(self: *Display) void {
    const gfx = gk.gfx;

    gfx.beginPass(.{ .color = gk.math.Color.black });

    gfx.draw.tex(self.base.voyager2, .{ .x = 0, .y = 0 });

    self.drawTop();
    self.drawOLED();

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
        // TODO: bold if value is true
        gk.gfx.draw.textOptions(name, self.display.base.fontbook, .{
            .x = self.left + @intToFloat(f32, DisplayBase.checkbox_size + DisplayBase.checkbox_text_gap),
            .y = self.top,
            .alignment = .left_middle,
            .color = DisplayBase.white,
        });

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

fn drawTop(self: *Display) void {
    var tds = TopDrawState.start(self);
    tds.check("power on", self.sh1107.power);
    tds.check("dc/dc on", self.sh1107.dcdc);
    tds.fmt("dclk", "{d}% {d}x", .{ @enumToInt(self.sh1107.dclk_freq), self.sh1107.dclk_ratio });
    tds.fmt("pre/dis", "{d}/{d}", .{ self.sh1107.precharge_period, self.sh1107.discharge_period });
    tds.fmt("vcom desel", "{x:0>2}", .{self.sh1107.vcom_desel});

    tds.row();
    tds.check("all on", self.sh1107.all_on);
    tds.check("reversed", self.sh1107.reversed);
    tds.fmt("contrast", "{x:0>2}", .{self.sh1107.contrast});

    tds.row();
    tds.fmt("start", "{x:0>2}/{x:0>2}", .{ self.sh1107.start_line, self.sh1107.start_column });
    tds.fmt("address", "{x:0>2}/{x:0>2}", .{ self.sh1107.page_address, self.sh1107.column_address });
    tds.fmt("mode", "{s}", .{self.sh1107.addressing_mode.str()});
    tds.fmt("multiplex", "{x:0>2}", .{self.sh1107.multiplex});

    tds.row();
    tds.check("seg remap", self.sh1107.segment_remap);
    tds.check("com rev", self.sh1107.com_scan_reversed);
}

fn dtStart(self: *Display) void {
    self.base.dtStart();
}

fn drawOLED(self: *Display) void {
    if (self.img_stale) {
        self.img.setData(gk.math.Color, &self.idata);
        self.img_stale = false;
    }

    if (self.sh1107.power) {
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

        gk.gfx.draw.texScale(
            self.img,
            .{
                .x = @intToFloat(f32, DisplayBase.padding + DisplayBase.border_width + if (self.sh1107.com_scan_reversed) DisplayBase.i2c_width * DisplayBase.display_scale else 0),
                .y = @intToFloat(f32, DisplayBase.padding + DisplayBase.border_width + DisplayBase.top_area),
            },
            // TODO: scale X only when com scan reversed
            // DisplayBase.display_scale * if (self.sh1107.com_scan_reversed) -1 else 1,
            @intToFloat(f32, DisplayBase.display_scale),
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

pub fn process_cmd(self: *Display, cmd: Cmd.Command) void {
    switch (cmd) {
        .SetLowerColumnAddress => |lower| {
            self.sh1107.column_address = (self.sh1107.column_address & 0x70) | lower;
        },
        .SetHigherColumnAddress => |higher| {
            self.sh1107.column_address = (self.sh1107.column_address & 0x0F) | (@as(u7, higher) << 4);
        },
        .DisplayOn => |on| {
            self.sh1107.power = on;
        },
        .SetPageAddress => |page| {
            self.sh1107.page_address = page;
        },
    }
}

pub fn process_data(self: *Display, data: u8) void {
    _ = data;
    _ = self;
}
