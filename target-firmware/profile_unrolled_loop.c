/*
 * emfi-profiler_assy.c
 *
 * Description:
 * Unrolled loop that increments a counter in register r7 a predefined amount of times (1000 by default).
 * Implemented in assembly. Developed for usage with STM32 microprocessor.
 * No compatibility guarantees forother architectures.
 *
 * Communication:
 * 1. Reset Signal (sent on startup):
 *    - At program start, the MCU sends a reset sequence using send_reset_sequence().
 *    - Purpose: Nnotify the host that the device has initialized and is ready
 *      to receive commands and allow the host to detect when a glitch caused a reset.
 *
 *  2. Host sends a start packet:
 *       - Command: 's'
 *       - Data:    None
 *       - Action:  MCU raises trigger GPIO and begins unrolled loop
 *
 *  3. MCU performs nested loop:
 *       - Trigger GPIO set high at start, low at end
 *       - Loop counter incremented specified amount of times (1000 by default)
 *
 *  4. MCU sends a response packet:
 *       - If loop count matches TOTAL_COUNT:
 *           - Command: 'e' (end signal)
 *           - Data:    None
 *       - If loop count does not match:
 *           - Command: 'f' (fault)
 *           - Data:    unsigned int (usually 4 bytes) containing the actual counter value
 *
 *  * Configuration:
 *       - NUM_EXECUTIONS (1000): Number of additions to perform (nested loop count).
 *                                Can only be one of  (10, 100, 1000, 10000)!
 */

#include "hal.h"
#include "hal/stm32f4-hal.h"
#include "simpleserial/simpleserial.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define setup_trigger() inline_gpio_mode_setup(GPIOA, GPIO_MODE_OUTPUT, GPIO_PUPD_PULLDOWN, GPIO12)
#define set_trigger() inline_gpio_set(GPIOA, GPIO12)
#define clear_trigger() inline_gpio_clear(GPIOA, GPIO12)

#define ADD_COMMAND "add r7, r7, #1;"

#define o ADD_COMMAND
#define t o o o o o o o o o o
#define h t t t t t t t t t t
#define d h h h h h h h h h h
#define x d d d d d d d d d d

#define ADD_10    t
#define ADD_100   h
#define ADD_1000  d
#define ADD_10000 x

// Dispatch is needed to treat ADD_##N as macro and keep expanding
#define NESTED_LOOP_MACRO_DISPATCH(N) ADD_##N
#define NESTED_LOOP_MACRO(N) NESTED_LOOP_MACRO_DISPATCH(N)

// +-----------------------------------------+
// |             CONFIG VARIABLES            |
// +-----------------------------------------+
#define NUM_EXECUTIONS 100 // Can only be 10, 100 or 1000, 10000 without modification to above defines

int main(void)
{
    platform_init();
    init_uart();
    setup_trigger();
    send_reset_sequence();

    char uart_ret;
    while (1)
    {
        uint8_t cmd;
        size_t dummy_len;
        int res = readpacket(&cmd, NULL, &dummy_len); // Read start signal
        if (res == 0 && cmd == 's')
        {
            send_ack(cmd); // Acknowledge start signal

            volatile unsigned int counter = 0;

            set_trigger(); // Raise trigger

            asm volatile (
                "mov r7, #0;" // Set r7 to 0
                NESTED_LOOP_MACRO(NUM_EXECUTIONS) // Unrolled loop
                "mov %[counter], r7;" // Set counter variable to r7

                : [counter] "=r" (counter) // Refer to variable counter from c code as counter in assembly code
                :
                : "r7"
            );

            clear_trigger(); // Lower trigger

            if (counter != NUM_EXECUTIONS){
                sendpacket('f', (const uint8_t *)&counter, sizeof(counter)); // Fault packet
            }
            else {
                sendpacket('e', NULL, 0); // End signal
            }
        }
    }
}
