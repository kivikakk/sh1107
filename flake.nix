{
  description = "Development shell for sh1107";

  inputs = {
    nixpkgs.follows = "hdx/nixpkgs";
    flake-compat = {
      url = github:edolstra/flake-compat;
      flake = false;
    };
    hdx.url = github:charlottia/hdx?ref=v0.1;
    hdx.inputs.amaranth.url = github:charlottia/amaranth?ref=rfc-2-implement;
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
        zig-overlay = inputs.zig.packages.${prev.system};
      })
    ];
  in
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = import nixpkgs {inherit overlays system;};
      hdx = pkgs.hdx.default;
      inherit (pkgs) lib;
      inherit (hdx) python;
      zig =
        if pkgs.stdenv.isDarwin
        then pkgs.zig-overlay.master
        else pkgs.zig;
    in rec {
      formatter = pkgs.alejandra;

      packages.default = python.pkgs.buildPythonPackage {
        name = "sh1107";

        format = "pyproject";
        src = ./.;

        nativeBuildInputs = builtins.attrValues ({
            inherit
              (python.pkgs)
              setuptools
              black
              isort
              ;

            inherit
              (pkgs.nodePackages)
              pyright
              ;

            inherit
              (pkgs)
              dfu-util
              ;

            inherit
              hdx
              zig
              ;
          }
          // lib.optionalAttrs (pkgs.stdenv.isDarwin) {
            inherit (pkgs) xcbuild;
          });

        buildInputs =
          (builtins.attrValues {
            inherit
              (pkgs)
              SDL2
              iconv
              ;
            inherit zig;
          })
          ++ lib.optionals (pkgs.stdenv.isDarwin) (with pkgs.darwin.apple_sdk.frameworks; [
            OpenGL
            ForceFeedback
            CoreGraphics
            CoreVideo
            MetalKit
            Cocoa
            IOKit
            AudioToolbox
            AppKit
            CoreAudio
            # CoreHaptics XXX
            Metal
            QuartzCore
            Carbon
            GameController
            Foundation
            Quartz
          ]);

        dontAddExtraLibs = true;

        preBuild = ''
          export ZIG_GLOBAL_CACHE_DIR="$TMPDIR/zig"
        '';

        doCheck = true;

        pythonImportsCheck = ["sh1107"];

        checkPhase = ''
          BOARDS=( icebreaker orangecrab )
          SPEEDS=( 100000 400000 )
          export CI=1

          set -euo pipefail

          echo "--- Unit tests."
          python -m sh1107 test

          for board in "''${BOARDS[@]}"; do
            for speed in "''${SPEEDS[@]}"; do
              echo "--- Building $board @ $speed."
              python -m sh1107 build "$board" -s "$speed"
            done
          done

          for opts in "-c" "-cfi"; do
            echo "--- Building Virtual SH1107 ($opts)."
            python -m sh1107 vsh "$opts"
            # On Darwin, nix build may appear to fail, but the binary output looks OK.
            # A true failure would exit non-zero?
          done

          echo "--- Formal verification."
          python -m sh1107 formal

          echo "--- All passed."
        '';
      };

      checks.default = packages.default;

      devShells.default = packages.default;
    });
}
