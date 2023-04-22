#include <oled_i2c.cc>

using namespace cxxrtl_design;

extern "C" {
extern int vsh();
}

int vsh() {
  p_top top;

  for (int i = 0; i < 1000; ++i) {
    top.p_clk.set(!top.p_clk);
    top.step();
  }

  return 42;
}
