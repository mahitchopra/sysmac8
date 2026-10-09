# sim/Makefile
SIM ?= icarus
TOPLEVEL_LANG ?= verilog

# Paths
VERILOG_SOURCES += $(PWD)/../rtl/arithmetic/multiplier_top.v
VERILOG_SOURCES += $(PWD)/../rtl/arithmetic/mult_array_8x8.v
VERILOG_SOURCES += $(PWD)/../rtl/arithmetic/mult_booth_8x8.v
VERILOG_SOURCES += $(PWD)/../rtl/core/pe.v
VERILOG_SOURCES += $(PWD)/../rtl/core/skew_registers.v
VERILOG_SOURCES += $(PWD)/../rtl/core/systolic_grid_4x4.v

COMPILE_ARGS += -Pmultiplier_top.ARCH=\"BOOTH_WALLACE\"

TOPLEVEL = systolic_grid_4x4
COCOTB_TEST_MODULES = tb_systolic

include $(shell cocotb-config --makefiles)/Makefile.sim