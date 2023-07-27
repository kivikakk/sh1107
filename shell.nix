{pkgs ? import <nixpkgs> {}}: let
  hdx = import (pkgs.fetchFromGitHub {
    owner = "charlottia";
    repo = "hdx";
    rev = "116f2cef9cdc75a33c49c578d3b93b19e68597a7";
    sha256 = "THrX3H1368OP+SXRb+S+cczvCbXubF/5s50VhrtDQbk=";
  }) {};
in
  pkgs.mkShell {
    name = "sh1107";
    nativeBuildInputs = [
      hdx
      pkgs.zig
    ];
  }
