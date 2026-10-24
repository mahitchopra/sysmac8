SIM ?= icarus
TOPLEVEL_LANG = verilog
TEST ?= systolic
ARCH ?= BOOTH_WALLACE

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
    $(RTL)/top/argmax.v \
    $(RTL)/top/sysmac8_top.v

ifeq ($(TEST),multiplier)
    TOPLEVEL = multiplier_top
    COCOTB_TEST_MODULES = tb_multiplier
    VERILOG_SOURCES = $(ARITH_SOURCES)
    COMPILE_ARGS += -Pmultiplier_top.ARCH=\"$(ARCH)\"
    SIM_BUILD = $(ROOT)/sim_build/multiplier_$(ARCH)

else ifeq ($(TEST),multiplier_array)
    TOPLEVEL = multiplier_top
    COCOTB_TEST_MODULES = tb_multiplier
    VERILOG_SOURCES = $(ARITH_SOURCES)
    COMPILE_ARGS += -Pmultiplier_top.ARCH=\"ARRAY\"
    SIM_BUILD = $(ROOT)/sim_build/multiplier_ARRAY

else ifeq ($(TEST),multiplier_booth)
    TOPLEVEL = multiplier_top
    COCOTB_TEST_MODULES = tb_multiplier
    VERILOG_SOURCES = $(ARITH_SOURCES)
    COMPILE_ARGS += -Pmultiplier_top.ARCH=\"BOOTH_WALLACE\"
    SIM_BUILD = $(ROOT)/sim_build/multiplier_BOOTH_WALLACE

else ifeq ($(TEST),requantizer)
    TOPLEVEL = requantizer
    COCOTB_TEST_MODULES = tb_requantizer
    VERILOG_SOURCES = $(RTL)/core/requantizer.v

else ifeq ($(TEST),pe)
    TOPLEVEL = pe
    COCOTB_TEST_MODULES = tb_pe
    VERILOG_SOURCES = $(ARITH_SOURCES) $(RTL)/core/pe.v
    COMPILE_ARGS += -Ppe.ARCH=\"$(ARCH)\"

else ifeq ($(TEST),systolic)
    TOPLEVEL = systolic_grid_4x4
    COCOTB_TEST_MODULES = tb_systolic
    VERILOG_SOURCES = $(GRID_SOURCES)
    COMPILE_ARGS += -Psystolic_grid_4x4.ARCH=\"$(ARCH)\"

else ifeq ($(TEST),grid_mac)
    TOPLEVEL = systolic_grid_4x4
    COCOTB_TEST_MODULES = tb_grid_mac
    VERILOG_SOURCES = $(GRID_SOURCES)
    COMPILE_ARGS += -Psystolic_grid_4x4.ARCH=\"$(ARCH)\"
    SIM_BUILD = $(ROOT)/sim_build/grid_mac

else ifeq ($(TEST),controller)
    TOPLEVEL = controller_fsm
    COCOTB_TEST_MODULES = tb_controller
    VERILOG_SOURCES = $(RTL)/control/controller_fsm.v

else ifeq ($(TEST),top)
    TOPLEVEL = sysmac8_top
    COCOTB_TEST_MODULES = tb_top
    VERILOG_SOURCES = $(TOP_SOURCES)
    COMPILE_ARGS += -Psysmac8_top.ARCH=\"$(ARCH)\"

else ifeq ($(TEST),top_mac)
    TOPLEVEL = sysmac8_top
    COCOTB_TEST_MODULES = tb_top_mac
    VERILOG_SOURCES = $(TOP_SOURCES)
    COMPILE_ARGS += -Psysmac8_top.ARCH=\"$(ARCH)\"

else ifeq ($(TEST),k_tile_accum)
    TOPLEVEL = sysmac8_top
    COCOTB_TEST_MODULES = tb_k_tile_accum
    VERILOG_SOURCES = $(TOP_SOURCES)
    COMPILE_ARGS += -Psysmac8_top.ARCH=\"$(ARCH)\"
    SIM_BUILD = $(ROOT)/sim_build/k_tile_accum

else ifeq ($(TEST),layer1_golden)
    TOPLEVEL = sysmac8_top
    COCOTB_TEST_MODULES = tb_layer1_golden
    VERILOG_SOURCES = $(TOP_SOURCES)
    COMPILE_ARGS += -Psysmac8_top.ARCH=\"$(ARCH)\"
    SIM_BUILD = $(ROOT)/sim_build/layer1_golden

else ifeq ($(TEST),mnist_infer)
    TOPLEVEL = sysmac8_top
    COCOTB_TEST_MODULES = tb_mnist_infer
    VERILOG_SOURCES = $(TOP_SOURCES)
    COMPILE_ARGS += -Psysmac8_top.ARCH=\"$(ARCH)\"
    SIM_BUILD = $(ROOT)/sim_build/mnist_infer_$(ARCH)

else
    $(error Unknown TEST='$(TEST)'. Choose multiplier, multiplier_array, multiplier_booth, requantizer, pe, systolic, grid_mac, controller, top, top_mac, k_tile_accum, layer1_golden, or mnist_infer)
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
