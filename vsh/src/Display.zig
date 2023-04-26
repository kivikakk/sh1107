const std = @import("std");
const gk = @import("gamekit");

const DisplayBase = @import("./DisplayBase.zig");
const Cxxrtl = @import("./Cxxrtl.zig");
const SH1107 = @import("./SH1107.zig");

base: DisplayBase,
cxxrtl: Cxxrtl,
sh1107: SH1107,

idata: [DisplayBase.i2c_width * DisplayBase.i2c_height]gk.math.Color = [_]gk.math.Color{DisplayBase.black} ** (DisplayBase.i2c_width * DisplayBase.i2c_height),
img: gk.gfx.Texture,
img_stale: bool = true,

pub fn init() !@This() {
    const base = try DisplayBase.init();
    const cxxrtl = Cxxrtl.init();

    const img = gk.gfx.Texture.init(DisplayBase.i2c_width, DisplayBase.i2c_height);

    return .{
        .base = base,
        .cxxrtl = cxxrtl,
        .sh1107 = .{},
        .img = img,
    };
}

pub fn deinit(self: @This()) void {
    self.cxxrtl.deinit();
}

pub fn update(self: *@This()) void {
    const clk = self.cxxrtl.get("clk");
    const swi = self.cxxrtl.get("switch");
    const last_cmd = self.cxxrtl.get("o_last_cmd");
    _ = last_cmd;
    const oled_result = self.cxxrtl.get("oled o_result");
    _ = oled_result;

    for (0..2) |i| {
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

        self.cxxrtl.step();
        // std.debug.print("step {}: clk {}, last_cmd {}, oled_result {}\n", .{ i, clk.*.curr[0], last_cmd.*.curr[0], oled_result.*.curr[0] });
    }
}

pub fn render(self: *@This()) void {
    const gfx = gk.gfx;

    gfx.beginPass(.{ .color = gk.math.Color.black });

    gfx.draw.tex(self.base.voyager2, .{ .x = 0, .y = 0 });

    gfx.draw.textOptions("Hola!", self.base.fontbook, .{
        .x = 20,
        .y = 40,
        .sx = 1,
        .sy = 1,
        .alignment = .left,
    });

    // TODO: draw_top
    self.drawOLED();

    gfx.endPass();
}

fn drawOLED(self: *@This()) void {
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
