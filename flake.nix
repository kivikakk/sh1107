{
  description = "Development shell for sh1107";

  inputs = {
    nixpkgs.follows = "hdx/nixpkgs";
    flake-compat = {
      url = github:edolstra/flake-compat;
      flake = false;
    };
    hdx.url = github:charlottia/hdx;
    zig.url = github:mitchellh/zig-overlay;
  };

  outputs = inputs @ {
    self,
    nixpkgs,
    flake-utils,
    flake-compat,
    ...
  }: let
    overlays = [
      (final: prev: {
        hdx = inputs.hdx.packages.${prev.system};
        zig = inputs.zig.packages.${prev.system};
      })
    ];
  in
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = import nixpkgs {inherit overlays system;};
    in {
      formatter = pkgs.alejandra;

      devShells.default = pkgs.mkShell {
        name = "sh1107";
        nativeBuildInputs = with pkgs; [
          hdx.default
          zig.master
          # XXX Due to https://github.com/ziglang/zig/issues/14569, vsh doesn't
          # build on macOS.
        ];
      };
    });
}
