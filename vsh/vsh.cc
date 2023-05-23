#include "sh1107.cc"
#include <iostream>

namespace cxxrtl_design {

struct bb_p_i2c_impl : public bb_p_i2c {
  enum {
    STATE_IDLE,
    STATE_X,
  } state;

  enum {
    FIFO_STATE_EMPTY,
    FIFO_STATE_FULL,
  } fifo_state;

  uint16_t fifo_value;

  bb_p_i2c_impl() : bb_p_i2c() {
    // TODO
  }

  void reset() override {
    state = STATE_IDLE;
    fifo_state = FIFO_STATE_EMPTY;
    fifo_value = 0u;

    p_fifo__r__rdy = wire<1>{0u};
    p_fifo__w__rdy = wire<1>{1u};
    p_ack = wire<1>{0u};
    p_busy = wire<1>{0u};
  }

  bool eval() override {
    // TODO(Ch): I guess we need to specify some kind of cycle delay count
    // so we don't prematurely end transactions.
    // OR!! What if we actually included an "end transaction" message??
    bool converged = true;
    bool posedge_p_clk = this->posedge_p_clk();

    if (posedge_p_clk) {
      switch (this->fifo_state) {
      case FIFO_STATE_EMPTY: {
        if (p_fifo__w__en) {
          std::cerr << "bb_p_i2c: FIFO loading " << p_fifo__w__data << "\n";
          this->fifo_value = p_fifo__w__data.get<uint16_t>();
          this->fifo_state = FIFO_STATE_FULL;
          p_fifo__w__rdy.next = value<1>{0u};
          p_fifo__r__rdy.next = value<1>{1u};
        }
        break;
      }
      case FIFO_STATE_FULL: {
        break;
      }
      }

      switch (this->state) {
      case STATE_IDLE: {
        if (p_stb) {
          p_busy.next = value<1>{1u};
          p_ack.next = value<1>{0u};
          this->state = STATE_X;
        }
        break;
      }
      case STATE_X: {
        if (this->fifo_state == FIFO_STATE_EMPTY) {
          std::cerr << "bb_p_i2c: ERR: FIFO empty?\n";
        } else {
          std::cerr << "bb_p_i2c: reading FIFO: " << fifo_value << "\n";
          fifo_state = FIFO_STATE_EMPTY;
          p_fifo__w__rdy.next = value<1>{1u};
          p_fifo__r__rdy.next = value<1>{0u};
        }
        state = STATE_IDLE;
        break;
      }
      }
    }

    return converged;
  }

  bool commit() override {
    bool changed = false;
    if (p_fifo__r__rdy.commit())
      changed = true;
    if (p_fifo__w__rdy.commit())
      changed = true;
    if (p_ack.commit())
      changed = true;
    if (p_busy.commit())
      changed = true;
    prev_p_clk = p_clk;
    return changed;
  }
};

std::unique_ptr<bb_p_i2c> bb_p_i2c::create(std::string name,
                                           metadata_map parameters,
                                           metadata_map attributes) {
  return std::make_unique<bb_p_i2c_impl>();
}

} // namespace cxxrtl_design
