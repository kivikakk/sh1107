from abc import ABCMeta, abstractmethod
import sys
import subprocess
import traceback
from typing import List, Tuple

from amaranth import Elaboratable, Signal, Module
from amaranth.back import rtlil
from amaranth.hdl import Fragment
from amaranth.sim import Simulator
from amaranth_boards.icebreaker import ICEBreakerPlatform

from .top import Top

SIM_CLOCK = 1e-6


class NEElaboratable(Elaboratable, metaclass=ABCMeta):
    @abstractmethod
    def prep_sim(self, sim: Simulator) -> List[Signal]:
        pass

    @classmethod
    @abstractmethod
    def formal(cls) -> Tuple[Module, List[Signal]]:
        pass


def main(cls: NEElaboratable):
    if len(sys.argv) != 2 or sys.argv[1] not in ["sim", "formal", "build"]:
        print(f"Usage: python {sys.argv[0]} sim|formal|build")
        sys.exit(1)

    def outfile(ext):
        return sys.argv[0].replace(".py", ext)

    if sys.argv[1] == "sim":
        args, kwargs = getattr(cls, 'sim_args', ([], {}))
        dut = cls(*args, **kwargs)
        sim = Simulator(dut)
        traces = dut.prep_sim(sim)

        gtkw_file = outfile(".gtkw")
        with sim.write_vcd(outfile(".vcd"), gtkw_file=gtkw_file, traces=traces):
            try:
                sim.run()
            except AssertionError as e:
                traceback.print_exception(e)

        if sys.platform == "darwin":
            cmd = f"open {gtkw_file}"
        else:
            cmd = gtkw_file
        subprocess.run(cmd, shell=True)

    elif sys.argv[1] == "formal":
        design, ports = cls.formal()
        fragment = Fragment.get(design, None)
        output = rtlil.convert(fragment, ports=ports)
        with open(outfile(".il"), "w") as f:
            f.write(output)

        sby_file = outfile(".sby")
        subprocess.run(f"sby -f {sby_file}", shell=True)

    else:
        ICEBreakerPlatform().build(cls(), do_program=True)


if __name__ == "__main__":
    main(Top)
