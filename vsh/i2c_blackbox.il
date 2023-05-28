attribute \cxxrtl_blackbox 1
attribute \blackbox 1
module \i2c
    attribute \cxxrtl_edge "p"
    wire input 1 \clk

    wire width 9 input 2 \in_fifo_w_data
    wire input 3 \in_fifo_w_en
    wire input 4 \stb
    wire input 5 \ack_in

    attribute \cxxrtl_sync 1
    wire output 6 \busy

    attribute \cxxrtl_sync 1
    wire output 7 \ack

    attribute \cxxrtl_sync 1
    wire output 8 \in_fifo_w_rdy
end
