# sim/Makefile
SIM ?= icarus
TOPLEVEL_LANG ?= verilog

# Paths
VERILOG_SOURCES += $(PWD)/../rtl/arithmetic/multiplier_top.v
VERILOG_SOURCES += $(PWD)/../rtl/arithmetic/mult_array_8x8.v

TOPLEVEL = multiplier_top
COCOTB_TEST_MODULES = tb_multiplier

include $(shell cocotb-config --makefiles)/Makefile.sim