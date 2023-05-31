attribute \cxxrtl_blackbox 1
attribute \blackbox 1
module \i2c
    attribute \cxxrtl_edge "p"
    wire input 1 \clk

    wire input 2 width 9 \in_fifo_w_data
    wire input 3 \in_fifo_w_en
    wire input 4 \out_fifo_r_en

    wire input 5 \stb

    wire input 6 \bb_in_ack
    wire input 7 width 8 \bb_in_out_fifo_data
    wire input 8 \bb_in_out_fifo_stb

    attribute \cxxrtl_sync 1
    wire output 9 \busy

    attribute \cxxrtl_sync 1
    wire output 10 \ack

    attribute \cxxrtl_sync 1
    wire output 11 \in_fifo_w_rdy

    attribute \cxxrtl_sync 1
    wire output 12 \out_fifo_r_rdy

    attribute \cxxrtl_sync 1
    wire output 13 width 8 \out_fifo_r_data
end
