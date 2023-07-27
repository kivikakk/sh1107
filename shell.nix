{pkgs ? import <nixpkgs> {}}: let
  hdx = import (pkgs.fetchFromGitHub {
    owner = "charlottia";
    repo = "hdx";
    rev = "116f2cef9cdc75a33c49c578d3b93b19e68597a7";
    sha256 = "THrX3H1368OP+SXRb+S+cczvCbXubF/5s50VhrtDQbk=";
  }) {};

  zig-overlay = import (pkgs.fetchFromGitHub {
    owner = "mitchellh";
    repo = "zig-overlay";
    rev = "ad3cdf96799c2c34e283feaf491124655c8edcd0";
    sha256 = "RNC6awMAIWlCnB0HZTJpie1v+mM9sOg+vFiIgF6r/f8=";
  }) {};
in
  pkgs.mkShell {
    name = "sh1107";
    nativeBuildInputs = [
      hdx
      zig-overlay.master
      # XXX Due to https://github.com/ziglang/zig/issues/14569, vsh doesn't build on macOS.
    ];
  }
