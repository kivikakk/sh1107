const std = @import("std");
const atomic = std.atomic;
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
stop_signal: atomic.Value(bool),
press_signal: atomic.Value(u8),
sh1107_mutex: std.Thread.Mutex = .{},
sh1107: SH1107,

idata_mutex: std.Thread.Mutex = .{},
idata: [DisplayBase.i2c_width * DisplayBase.i2c_height]gk.math.Color = [_]gk.math.Color{DisplayBase.black} ** (DisplayBase.i2c_width * DisplayBase.i2c_height),
idata_stale: atomic.Value(bool),

pub fn start() !*FPGAThread {
    var fpga_thread = try std.heap.c_allocator.create(FPGAThread);
    fpga_thread.* = .{
        .thread = undefined,
        .stop_signal = atomic.Value(bool).init(false),
        .press_signal = atomic.Value(u8).init(0),
        .sh1107 = .{},
        .idata_stale = atomic.Value(bool).init(true),
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

pub fn press_switch_connector(self: *FPGAThread, which: u8) void {
    self.press_signal.store(which, .Monotonic);
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
        const px = ((pxw.value >> @as(u3, @truncate(i))) & 1) == 1;
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
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();

    const allocator = gpa.allocator();

    var state = State.init(allocator, fpga_thread) catch @panic("State.init threw");
    defer state.deinit();

    state.run() catch @panic("FPGA thread threw");
}

const State = struct {
    fpga_thread: *FPGAThread,
    allocator: std.mem.Allocator,

    cxxrtl: Cxxrtl,
    vcd: ?Cxxrtl.Vcd,

    switch_connectors: []SwitchConnector,
    oled_connector: OLEDConnector,

    fn init(allocator: std.mem.Allocator, fpga_thread: *FPGAThread) !State {
        const cxxrtl = Cxxrtl.init();

        var vcd: ?Cxxrtl.Vcd = null;
        if (main.write_vcd) {
            vcd = Cxxrtl.Vcd.init(cxxrtl);
        }

        var switch_connectors = std.ArrayList(SwitchConnector).init(allocator);
        defer switch_connectors.deinit();

        var i: usize = 0;
        while (true) {
            const name = try std.fmt.allocPrintZ(allocator, "switch_{}", .{i});
            defer allocator.free(name);

            if (cxxrtl.find(bool, name)) |swi| {
                try switch_connectors.append(SwitchConnector.init(swi));
                i += 1;
            } else {
                break;
            }
        }

        const oled_connector = OLEDConnector.init(cxxrtl, 0x3c);

        return .{
            .fpga_thread = fpga_thread,
            .allocator = allocator,

            .cxxrtl = cxxrtl,
            .vcd = vcd,

            .switch_connectors = try switch_connectors.toOwnedSlice(),
            .oled_connector = oled_connector,
        };
    }

    fn deinit(self: *State) void {
        self.allocator.free(self.switch_connectors);
    }

    fn run(self: *State) !void {
        const clk = self.cxxrtl.get(bool, "clk");

        if (self.vcd) |*vcd| {
            vcd.sample();
        }

        while (!self.fpga_thread.stop_signal.load(.Monotonic)) {
            clk.next(true);

            for (self.switch_connectors, 1..) |*swicon, i| {
                if (self.fpga_thread.press_signal.cmpxchgStrong(@as(u8, @intCast(i)), 0, .Monotonic, .Monotonic) == null) {
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
        }

        if (self.vcd) |*vcd| {
            defer vcd.deinit();

            const buffer = try vcd.read(self.allocator);
            defer self.allocator.free(buffer);

            var file = try std.fs.cwd().createFile("vsh.vcd", .{});
            defer file.close();

            try file.writeAll(buffer);
        }
    }
};
