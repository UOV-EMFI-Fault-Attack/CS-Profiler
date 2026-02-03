/*
 * emfi-profiler_loop.c
 *
 * Description:
 * Increments a counter in a two-stage nested loop.
 * Afterwords the counter is validated. If abnormal a fault packet is sent,
 * including the counter value. Otherwise simple end signal is sent.
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
 *       - Action:  MCU raises trigger GPIO and begins nested loop
 *
 *  3. MCU performs nested loop:
 *       - Trigger GPIO set high at start, low at end
 *       - Loop counter incremented OUTER_COUNT * INNER_COUNT times
 *
 *  4. MCU sends a response packet:
 *       - If loop count matches TOTAL_COUNT:
 *           - Command: 'e' (end signal)
 *           - Data:    None
 *       - If loop count does not match TOTAL_COUNT:
 *           - Command: 'f' (fault)
 *           - Data:    unsigned int (usually 4 bytes) containing the actual counter value
 *
 * Configuration:
 *       - OUTER_COUNT (500): Number of iterations for the outer loop
 *       - INNER_COUNT (500): Number of iterations for the inner loop
 */

#include "hal.h"
#include "hal/stm32f4-hal.h"
#include "simpleserial/simpleserial.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>

#define setup_trigger() inline_gpio_mode_setup(GPIOA, GPIO_MODE_OUTPUT, GPIO_PUPD_PULLDOWN, GPIO12)
#define set_trigger() inline_gpio_set(GPIOA, GPIO12)
#define clear_trigger() inline_gpio_clear(GPIOA, GPIO12)

#define TOTAL_COUNT (OUTER_COUNT * INNER_COUNT) // Make sure that 
// Compile-time check: ensure TOTAL_COUNT fits in unsigned int
#if TOTAL_COUNT > UINT_MAX
#error "TOTAL_COUNT is larger than the maximum value of unsigned int!"
#endif

// +-----------------------------------------+
// |             CONFIG VARIABLES            |
// +-----------------------------------------+
#define OUTER_COUNT 500 // Number of iterations for outer loop
#define INNER_COUNT 500 // Number of iterations for inner loop


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
            for (int i = 0; i < OUTER_COUNT; i++)
            {
                for (int j = 0; j < INNER_COUNT; j++)
                {
                    counter++;
                }
            }
            clear_trigger(); // Lower trigger

            if (counter != TOTAL_COUNT){
                sendpacket('f', (const uint8_t *)&counter, sizeof(counter)); // Fault packet
            }
            else {
                sendpacket('e', NULL, 0); // End signal
            }
        }
    }
}
