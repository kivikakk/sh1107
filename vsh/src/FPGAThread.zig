const std = @import("std");
const Atomic = std.atomic.Atomic;
const gk = @import("gamekit");

const main = @import("./main.zig");
const DisplayBase = @import("./DisplayBase.zig");
const Cxxrtl = @import("./Cxxrtl.zig");
const SH1107 = @import("./SH1107.zig");
const Cmd = @import("./Cmd.zig");

const SwitchConnector = @import("./SwitchConnector.zig");
const OLEDConnector = @import("./OLEDConnector.zig");

const FPGAThread = @This();

thread: std.Thread,
stop_signal: Atomic(bool),
press_signal: Atomic(bool),
sh1107_mutex: std.Thread.Mutex = .{},
sh1107: SH1107,

idata_mutex: std.Thread.Mutex = .{},
idata: [DisplayBase.i2c_width * DisplayBase.i2c_height]gk.math.Color = [_]gk.math.Color{DisplayBase.black} ** (DisplayBase.i2c_width * DisplayBase.i2c_height),
idata_stale: Atomic(bool),

pub fn start() !*FPGAThread {
    var fpga_thread = try std.heap.c_allocator.create(FPGAThread);
    fpga_thread.* = .{
        .thread = undefined,
        .stop_signal = Atomic(bool).init(false),
        .press_signal = Atomic(bool).init(false),
        .sh1107 = .{},
        .idata_stale = Atomic(bool).init(true),
    };
    const thread = try std.Thread.spawn(.{}, run, .{fpga_thread});
    fpga_thread.thread = thread;
    return fpga_thread;
}

pub fn stop(self: *FPGAThread) void {
    self.stop_signal.store(true, .Monotonic);
    self.thread.join();
    std.heap.c_allocator.destroy(self);
}

pub fn acquire_sh1107(self: *FPGAThread) SH1107 {
    self.sh1107_mutex.lock();
    defer self.sh1107_mutex.unlock();
    return self.sh1107;
}

pub fn press_switch_connector(self: *FPGAThread) void {
    self.press_signal.store(true, .Monotonic);
}

pub fn process_cmd(self: *FPGAThread, cmd: Cmd.Command) void {
    self.sh1107_mutex.lock();
    defer self.sh1107_mutex.unlock();
    self.sh1107.cmd(cmd);
}

pub fn process_data(self: *FPGAThread, data: u8) void {
    const pxw = pxw: {
        self.sh1107_mutex.lock();
        defer self.sh1107_mutex.unlock();
        break :pxw self.sh1107.data(data);
    };

    self.idata_mutex.lock();
    defer self.idata_mutex.unlock();
    defer self.idata_stale.store(true, .Release);
    for (0..8) |i| {
        const px = ((pxw.value >> @truncate(u3, i)) & 1) == 1;
        const x = pxw.column;
        const y = pxw.row + i;

        const off = y * DisplayBase.i2c_height + x;
        self.idata[off] = if (px)
            DisplayBase.white
        else
            DisplayBase.black;
    }
}

// Called with Thread.spawn.
fn run(fpga_thread: *FPGAThread) void {
    var state = State.init(fpga_thread);
    state.run() catch @panic("FPGAThread threw");
}

const State = struct {
    fpga_thread: *FPGAThread,

    cxxrtl: Cxxrtl,
    vcd: ?Cxxrtl.Vcd,
    switch_connector: ?SwitchConnector,
    oled_connector: OLEDConnector,

    fn init(fpga_thread: *FPGAThread) State {
        const cxxrtl = Cxxrtl.init();

        var vcd: ?Cxxrtl.Vcd = null;
        if (main.write_vcd) {
            vcd = Cxxrtl.Vcd.init(cxxrtl);
        }

        var switch_connector: ?SwitchConnector = null;
        if (cxxrtl.find(bool, "switch")) |swi| {
            switch_connector = SwitchConnector.init(swi);
        }

        const oled_connector = OLEDConnector.init(cxxrtl, 0x3c);

        return .{
            .fpga_thread = fpga_thread,

            .cxxrtl = cxxrtl,
            .vcd = vcd,
            .switch_connector = switch_connector,
            .oled_connector = oled_connector,
        };
    }

    fn run(self: *State) !void {
        var gpa = std.heap.GeneralPurposeAllocator(.{}){};
        defer _ = gpa.deinit();

        var allocator = gpa.allocator();

        const clk = self.cxxrtl.get(bool, "clk");
        const oled_result = self.cxxrtl.get(u2, "oled o_result");
        var last_oled_result = oled_result.curr();

        if (self.vcd) |*vcd| {
            vcd.sample();
        }

        while (!self.fpga_thread.stop_signal.load(.Monotonic)) {
            clk.next(true);
            if (self.switch_connector) |*swicon| {
                if (self.fpga_thread.press_signal.compareAndSwap(true, false, .Monotonic, .Monotonic) == null) {
                    swicon.press();
                }
                swicon.tick();
            }
            self.oled_connector.tick(self.fpga_thread);
            self.cxxrtl.step();

            if (self.vcd) |*vcd| {
                vcd.sample();
            }

            clk.next(false);
            self.cxxrtl.step();

            if (self.vcd) |*vcd| {
                vcd.sample();
            }

            const curr_oled_result = oled_result.curr();
            if (curr_oled_result != last_oled_result) {
                std.debug.print("oled_result -> {d}\n", .{curr_oled_result});
                last_oled_result = curr_oled_result;
            }
        }

        if (self.vcd) |*vcd| {
            defer vcd.deinit();

            var buffer = try vcd.read(allocator);
            defer allocator.free(buffer);

            var file = try std.fs.cwd().createFile("vsh.vcd", .{});
            defer file.close();

            try file.writeAll(buffer);
        }
    }
};
