#include "build/sh1107.h"
#include <iostream>

/**
 * Yawonk.
 */

extern "C" const uint8_t *spi_flash_content;
extern "C" uint32_t spi_flash_base;
extern "C" uint32_t spi_flash_length;

namespace cxxrtl_design {

struct bb_p_spifr_impl : public bb_p_spifr {
  // Similar to bb_p_i2c_impl::TICKS_TO_WAIT, but between each cycle with valid
  // data.
  const uint8_t COUNTDOWN_BETWEEN_BYTES = 2u;

  enum {
    STATE_IDLE,
    STATE_READ,
  } state;

  uint32_t address;
  uint16_t remaining;
  uint8_t countdown;

  void reset() override {
    this->state = STATE_IDLE;
    this->address = 0u;
    this->remaining = 0u;
    this->countdown = 0u;

    p_busy = wire<1>{0u};
    p_data = wire<8>{0u};
    p_valid = wire<1>{0u};
  }

  bool eval() override {
    bool converged = true;
    bool posedge_p_clk = this->posedge_p_clk();

    if (posedge_p_clk) {
      p_valid.next = value<1>{0u};

      switch (this->state) {
      case STATE_IDLE: {
        if (p_stb) {
          this->address = p_addr.get<uint32_t>();
          this->remaining = p_len.get<uint16_t>();

          if (this->address >= spi_flash_base &&
              this->address < spi_flash_base + spi_flash_length) {
            p_busy.next = value<1>{1u};
            this->state = STATE_READ;
            this->countdown = COUNTDOWN_BETWEEN_BYTES;
          }
        }
        break;
      }
      case STATE_READ: {
        if (--this->countdown == 0u) {
          if (this->remaining == 0u) {
            p_busy.next = value<1>{0u};
            this->state = STATE_IDLE;
          } else {
            this->countdown = COUNTDOWN_BETWEEN_BYTES;
            if (this->address - spi_flash_base < spi_flash_length)
              p_data.next =
                  value<8>{spi_flash_content[this->address - spi_flash_base]};
            else
              p_data.next = value<8>{0xffu};
            p_valid.next = value<1>{1u};

            ++this->address;
            --this->remaining;
          }
        }
        break;
      }
      }
    }

    return converged;
  }
};

std::unique_ptr<bb_p_spifr> bb_p_spifr::create(std::string name,
                                               metadata_map parameters,
                                               metadata_map attributes) {
  return std::make_unique<bb_p_spifr_impl>();
}

} // namespace cxxrtl_design
