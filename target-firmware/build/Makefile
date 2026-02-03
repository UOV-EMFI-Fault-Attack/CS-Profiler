# Hey Emacs, this is a -*- makefile -*-
#----------------------------------------------------------------------------
#
# Makefile for ChipWhisperer SimpleSerial-AES Program
#
#----------------------------------------------------------------------------
# On command line:
#
# make all = Make software.
#
# make clean = Clean out built project files.
#
# make coff = Convert ELF to AVR COFF.
#
# make extcoff = Convert ELF to AVR Extended COFF.
#
# make program = Download the hex file to the device, using avrdude.
#                Please customize the avrdude settings below first!
#
# make debug = Start either simulavr or avarice as specified for debugging,
#              with avr-gdb or avr-insight as the front end for debugging.
#
# make filename.s = Just compile filename.c into the assembler code only.
#
# make filename.i = Create a preprocessed source file for use in submitting
#                   bug reports to the GCC project.
#
# To rebuild project do "make clean" then "make all".
#----------------------------------------------------------------------------

PLATFORM=CW308_STM32F4
CRYPTO_TARGET=NONE
CRYPTO_OPTIONS=NONE

# Target file name (without extension).
# This is the base name of the compiled .hex file.
TARGET = emfi-profiler
BUILD_SRC ?= emfi-profiler_assy.c

# List C source files here.
# Header files (.h) are automatically pulled in.
VPATH += : ../
EXTRAINCDIRS += ../
VPATH += : ../hal
EXTRAINCDIRS += ../hal
VPATH += : ../simpleserial
EXTRAINCDIRS += ../simpleserial

COMMON_SRC = simpleserial.c
SRC += $(BUILD_SRC) $(COMMON_SRC)

FIRMWAREPATH = ../cw-deps/.
include $(FIRMWAREPATH)/simpleserial/Makefile.simpleserial
include $(FIRMWAREPATH)/Makefile.inc

.PHONY: unrolled_loop loop memcpy

unrolled_loop:
	@$(MAKE) BUILD_SRC=profile_unrolled_loop.c

loop:
	@$(MAKE) BUILD_SRC=profile_loop.c

memcpy:
	@$(MAKE) BUILD_SRC=profile_memcpy.c
