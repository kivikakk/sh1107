#include "sh1107.cc"
#include <iostream>

/**
 * NOTE: This file is **only** used if using the blackbox.  If launching vsh
 * with "driver.py vsh -i", build/sh1107.cc is used directly instead.
 *
 * This code is officially Not Poggers(tm).
 *
 * We emulate the external interface of i2c.py's I2C module for the benefit of
 * the rest of the design, rather than the benefit of the simulation.  The
 * simulation snoops our _inputs_ and uses those directly.
 */

namespace cxxrtl_design {

struct bb_p_i2c_impl : public bb_p_i2c {
  // NOTE(Ch): Wow! This is a very magic number! This specifies how many
  // posedges without FIFO activity to wait until we consider the transaction to
  // be done and bring "busy" low.  Whether this is sufficient will vary
  // depending on the users of the real I2C module, and how much leeway it gives
  // its users.  We might want to consider a rewrite where transaction ends are
  // signalled explicitly from the user, but that gets Fucky Wucky if they don't
  // actually give input data in time for the I2C bus.
  const uint16_t TICKS_TO_WAIT = 5u;

  enum {
    STATE_IDLE,
    STATE_BUSY,
  } state;

  uint16_t ticks_until_done;

  enum {
    FIFO_STATE_EMPTY,
    FIFO_STATE_FULL,
  } fifo_state;

  uint16_t fifo_value;

  void reset() override {
    state = STATE_IDLE;
    fifo_state = FIFO_STATE_EMPTY;
    fifo_value = 0u;

    p_busy = wire<1>{0u};
    p_ack = wire<1>{0u};
    p_fifo__w__rdy = wire<1>{1u};
  }

  bool eval() override {
    bool converged = true;
    bool posedge_p_clk = this->posedge_p_clk();

    if (posedge_p_clk) {
      p_ack.next = p_ack__in;

      switch (this->state) {
      case STATE_IDLE: {
        if (p_stb) {
          p_busy.next = value<1>{1u};
          this->state = STATE_BUSY;
          this->ticks_until_done = TICKS_TO_WAIT;
        }
        break;
      }
      case STATE_BUSY: {
        if (this->fifo_state == FIFO_STATE_FULL) {
          this->fifo_state = FIFO_STATE_EMPTY;
          this->ticks_until_done = TICKS_TO_WAIT;
          p_fifo__w__rdy.next = value<1>{1u};
        }

        if (--this->ticks_until_done == 0u) {
          p_busy.next = value<1>{0u};
          this->state = STATE_IDLE;
        }
        break;
      }
      }

      switch (this->fifo_state) {
      case FIFO_STATE_EMPTY: {
        if (p_fifo__w__en) {
          this->fifo_value = p_fifo__w__data.get<uint16_t>();
          this->fifo_state = FIFO_STATE_FULL;
          p_fifo__w__rdy.next = value<1>{0u};
        }
        break;
      }
      case FIFO_STATE_FULL: {
        break;
      }
      }
    }

    return converged;
  }
};

std::unique_ptr<bb_p_i2c> bb_p_i2c::create(std::string name,
                                           metadata_map parameters,
                                           metadata_map attributes) {
  return std::make_unique<bb_p_i2c_impl>();
}

} // namespace cxxrtl_design
