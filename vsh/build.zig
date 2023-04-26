const std = @import("std");
const gkBuild = @import("vendor/zig-gamekit/build.zig");

pub fn build(b: *std.Build) void {
    const yosys_data_dir = b.option([]const u8, "yosys_data_dir", "yosys data dir (e.g. per yosys-config --datdir)") orelse
        guess_yosys_data_dir(b);
    const cxxrtl_lib_path = b.option([]const u8, "cxxrtl_lib_path", "path to CXXRTL-compiled .o") orelse
        "../build/oled_i2c.o";

    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const exe = b.addExecutable(.{
        .name = "vsh",
        .root_source_file = .{ .path = "src/main.zig" },
        .target = target,
        .optimize = optimize,
    });
    exe.linkLibCpp();
    exe.addObjectFile(cxxrtl_lib_path);
    exe.addIncludePath(b.fmt("{s}/include", .{yosys_data_dir}));

    gkBuild.addGameKitToArtifact(b, exe, target, "vendor/zig-gamekit/");

    b.installArtifact(exe);

    const run_cmd = b.addRunArtifact(exe);

    run_cmd.step.dependOn(b.getInstallStep());

    if (b.args) |args| {
        run_cmd.addArgs(args);
    }

    const run_step = b.step("run", "Run the app");
    run_step.dependOn(&run_cmd.step);

    const unit_tests = b.addTest(.{
        .root_source_file = .{ .path = "src/main.zig" },
        .target = target,
        .optimize = optimize,
    });

    const run_unit_tests = b.addRunArtifact(unit_tests);

    const test_step = b.step("test", "Run unit tests");
    test_step.dependOn(&run_unit_tests.step);
}

fn guess_yosys_data_dir(b: *std.Build) []const u8 {
    const result = std.ChildProcess.exec(.{
        .allocator = b.allocator,
        .argv = &.{ "yosys-config", "--datdir" },
        .expand_arg0 = .expand,
    }) catch @panic("couldn't run yosys-config; please supply -Dyosys_data_dir");
    return std.mem.trim(u8, result.stdout, "\n");
}
