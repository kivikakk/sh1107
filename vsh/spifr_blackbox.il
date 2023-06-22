attribute \cxxrtl_blackbox 1
attribute \blackbox 1
module \spifr
    attribute \cxxrtl_edge "p"
    wire input 1 \clk

    wire input 2 width 24 \addr
    wire input 3 width 16 \len
    wire input 4 \stb

    attribute \cxxrtl_sync 1
    wire output 5 \busy

    attribute \cxxrtl_sync 1
    wire output 6 width 8 \data

    attribute \cxxrtl_sync 1
    wire output 7 \valid
end
