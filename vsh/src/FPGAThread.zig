const std = @import("std");
const Atomic = std.atomic.Atomic;
const gk = @import("gamekit");

const DisplayBase = @import("./DisplayBase.zig");
const Cxxrtl = @import("./Cxxrtl.zig");
const SH1107 = @import("./SH1107.zig");
const Cmd = @import("./Cmd.zig");

const SwitchConnector = @import("./SwitchConnector.zig");
const OLEDConnector = @import("./OLEDConnector.zig");

const FPGAThread = @This();

thread: std.Thread,
stop_signal: std.atomic.Atomic(bool),
press_signal: std.atomic.Atomic(bool),
sh1107_mutex: std.Thread.Mutex,
sh1107: SH1107,

pub fn start() !*FPGAThread {
    var fpga_thread = try std.heap.c_allocator.create(FPGAThread);
    fpga_thread.* = .{
        .thread = undefined,
        .stop_signal = Atomic(bool).init(false),
        .press_signal = Atomic(bool).init(false),
        .sh1107_mutex = .{},
        .sh1107 = .{},
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

pub fn process_data(self: *FPGAThread, data: u8) void {
    _ = data;
    _ = self;
}

fn run(fpga_thread: *FPGAThread) void {
    var state = State.init(fpga_thread);
    state.run();
}

const State = struct {
    fpga_thread: *FPGAThread,

    cxxrtl: Cxxrtl,
    switch_connector: ?SwitchConnector,
    oled_connector: OLEDConnector,

    fn init(fpga_thread: *FPGAThread) State {
        const cxxrtl = Cxxrtl.init();

        var switch_connector: ?SwitchConnector = null;
        if (cxxrtl.find(bool, "switch")) |swi| {
            switch_connector = SwitchConnector.init(swi);
        }

        const oled_connector = OLEDConnector.init(cxxrtl, 0x3c);

        return .{
            .fpga_thread = fpga_thread,

            .cxxrtl = cxxrtl,
            .switch_connector = switch_connector,
            .oled_connector = oled_connector,
        };
    }

    fn run(self: *State) void {
        const clk = self.cxxrtl.get(bool, "clk");
        const last_cmd = self.cxxrtl.get(u8, "o_last_cmd");
        _ = last_cmd;
        const oled_result = self.cxxrtl.get(u2, "oled o_result");
        var last_oled_result = oled_result.curr();

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

            clk.next(false);
            self.cxxrtl.step();

            const curr_oled_result = oled_result.curr();
            if (curr_oled_result != last_oled_result) {
                std.debug.print("oled_result -> {d}\n", .{curr_oled_result});
                last_oled_result = curr_oled_result;
            }
        }
    }
};
