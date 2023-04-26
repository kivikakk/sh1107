const Cxxrtl = @import("./Cxxrtl.zig");

object: Cxxrtl.Object(bool),
state: enum { Idle, Pressing, Releasing } = .Idle,

pub fn init(swi: Cxxrtl.Object(bool)) @This() {
    return .{
        .object = swi,
    };
}

pub fn tick(self: *@This()) void {
    switch (self.state) {
        .Idle => {},
        .Pressing => {
            self.state = .Releasing;
            self.object.next(true);
        },
        .Releasing => {
            self.state = .Idle;
            self.object.next(false);
        },
    }
}

pub fn press(self: *@This()) void {
    if (self.state == .Idle) {
        self.state = .Pressing;
    }
}
