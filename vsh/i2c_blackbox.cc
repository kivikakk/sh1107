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
 * simulation snoops _our inputs_ and uses those directly.
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
    IN_FIFO_STATE_EMPTY,
    IN_FIFO_STATE_FULL,
  } in_fifo_state;
  uint16_t in_fifo_value;

  enum {
    OUT_FIFO_STATE_EMPTY,
    OUT_FIFO_STATE_FULL,
  } out_fifo_state;
  uint8_t out_fifo_value;

  void reset() override {
    state = STATE_IDLE;
    in_fifo_state = IN_FIFO_STATE_EMPTY;
    in_fifo_value = 0u;
    out_fifo_state = OUT_FIFO_STATE_EMPTY;
    out_fifo_value = 0u;

    p_busy = wire<1>{0u};
    p_ack = wire<1>{1u};
    p_in__fifo__w__rdy = wire<1>{1u};
    p_out__fifo__r__rdy = wire<1>{0u};
    p_out__fifo__r__data = wire<8>{0u};
  }

  bool eval() override {
    bool converged = true;
    bool posedge_p_clk = this->posedge_p_clk();

    if (posedge_p_clk) {
      p_ack.next = p_bb__in__ack;

      if (p_out__fifo__r__en && out_fifo_state == OUT_FIFO_STATE_FULL) {
        out_fifo_state = OUT_FIFO_STATE_EMPTY;
        p_out__fifo__r__rdy.next = value<1>{0u};
      }

      if (p_bb__in__out__fifo__stb) {
        out_fifo_state = OUT_FIFO_STATE_FULL;
        out_fifo_value = p_bb__in__out__fifo__data.get<uint8_t>();
        p_out__fifo__r__rdy.next = value<1>{1u};
        p_out__fifo__r__data.next = value<8>{out_fifo_value};
      }

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
        if (this->in_fifo_state == IN_FIFO_STATE_FULL) {
          this->in_fifo_state = IN_FIFO_STATE_EMPTY;
          this->ticks_until_done = TICKS_TO_WAIT;
          p_in__fifo__w__rdy.next = value<1>{1u};
        }

        if (--this->ticks_until_done == 0u) {
          p_busy.next = value<1>{0u};
          this->state = STATE_IDLE;
        }
        break;
      }
      }

      switch (this->in_fifo_state) {
      case IN_FIFO_STATE_EMPTY: {
        if (p_in__fifo__w__en) {
          this->in_fifo_value = p_in__fifo__w__data.get<uint16_t>();
          this->in_fifo_state = IN_FIFO_STATE_FULL;
          p_in__fifo__w__rdy.next = value<1>{0u};
        }
        break;
      }
      case IN_FIFO_STATE_FULL: {
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
