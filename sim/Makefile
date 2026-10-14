SIM ?= icarus
TOPLEVEL_LANG = verilog
TEST ?= systolic

ROOT := $(abspath ..)
RTL := $(ROOT)/rtl

ARITH_SOURCES = \
    $(RTL)/arithmetic/multiplier_top.v \
    $(RTL)/arithmetic/mult_array_8x8.v \
    $(RTL)/arithmetic/mult_booth_8x8.v

CORE_SOURCES = \
    $(RTL)/core/pe.v \
    $(RTL)/core/skew_registers.v \
    $(RTL)/core/requantizer.v

CONTROL_SOURCES = \
    $(RTL)/control/controller_fsm.v \
    $(RTL)/control/accum_buffer.v \
    $(RTL)/control/buffer_ram.v

GRID_SOURCES = \
    $(ARITH_SOURCES) \
    $(CORE_SOURCES) \
    $(RTL)/core/systolic_grid_4x4.v

TOP_SOURCES = \
    $(GRID_SOURCES) \
    $(CONTROL_SOURCES) \
    $(RTL)/top/sysmac8_top.v

ifeq ($(TEST),requantizer)
    TOPLEVEL = requantizer
    COCOTB_TEST_MODULES = tb_requantizer
    VERILOG_SOURCES = $(RTL)/core/requantizer.v

else ifeq ($(TEST),pe)
    TOPLEVEL = pe
    COCOTB_TEST_MODULES = tb_pe
    VERILOG_SOURCES = $(ARITH_SOURCES) $(RTL)/core/pe.v

else ifeq ($(TEST),systolic)
    TOPLEVEL = systolic_grid_4x4
    COCOTB_TEST_MODULES = tb_systolic
    VERILOG_SOURCES = $(GRID_SOURCES)

else ifeq ($(TEST),grid_mac)
    TOPLEVEL = systolic_grid_4x4
    COCOTB_TEST_MODULES = tb_grid_mac
    VERILOG_SOURCES = $(GRID_SOURCES)
    SIM_BUILD = $(ROOT)/sim_build/grid_mac

else ifeq ($(TEST),controller)
    TOPLEVEL = controller_fsm
    COCOTB_TEST_MODULES = tb_controller
    VERILOG_SOURCES = $(RTL)/control/controller_fsm.v

else ifeq ($(TEST),top)
    TOPLEVEL = sysmac8_top
    COCOTB_TEST_MODULES = tb_top
    VERILOG_SOURCES = $(TOP_SOURCES)

else ifeq ($(TEST),top_mac)
    TOPLEVEL = sysmac8_top
    COCOTB_TEST_MODULES = tb_top_mac
    VERILOG_SOURCES = $(TOP_SOURCES)

else
    $(error Unknown TEST='$(TEST)'. Choose requantizer, pe, systolic, grid_mac, controller, top, or top_mac)
endif

include $(shell cocotb-config --makefiles)/Makefile.sim