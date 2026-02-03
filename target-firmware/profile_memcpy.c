/*
 * emfi-profiler_memcpy.c
 *
 * Description:
 * Copy data from a source buffer to a target buffer.
 * If target buffer is not equal to source buffer, a fault packet is sent.
 * Otherwise a simple end signal is sent.
 *
 * Communication:
 * 1. Reset Signal (sent on startup):
 *    - At program start, the MCU sends a reset sequence using
 *      send_reset_sequence()
 *    - Purpose: Notify the host that the device has initialized and is
 *      ready to receive commands, and allow the host to detect when a
 *      glitch caused a reset
 *
 * 2. Host sends a start packet:
 *    - Command: 's'
 *    - Data:    None
 *    - Action:  MCU raises trigger GPIO and performs memcpy()
 *
 * 3. MCU performs memcpy test:
 *    - Trigger GPIO set high at start, low at end
 *    - Source buffer is initialized with 0xBB
 *    - Target buffer is initialized with 0xAA
 *    - memcpy(target, src, sizeof(src)) is executed
 *
 * 4. MCU sends a response packet:
 *    - If memcpy result is correct:
 *        - Command: 'e' (end signal)
 *        - Data:    None
 *    - If memcpy result is corrupted:
 *        - Command: 'f' (fault)
 *        - Data:    Full target buffer (for analysis)
 *
 * Configuration:
 *       - BUFFER_SIZE (68): Size of the source and target buffers.
 *       - SRC_BUFFER_INIT_BYTE (0xAA): Byte that source buffer should be filled with before every memcpy.
 *       - TARGET_BUFFER_INIT_BYTE (0xBB): Byte that target buffer should be filled with before every memcpy.
 *       - SRC_BUFFER_INIT_SEQUENCE (undefined):
 *             Allows initialization of source and target buffer with custom data.
*              Should match BUFFER_SIZE, otherwise rest auto filled with zeros.
 *             Not defined by default, will overwrite `SRC_BUFFER_INIT_BYTE` when defined.
 *             Format: {0xAA, 0xAA, 0xAA, ...}
 *       - TARGET_BUFFER_INIT_SEQUENCE (undefined):
 *             Allows initialization of source and target buffer with custom data.
*              Should match BUFFER_SIZE, otherwise rest is auto filled with zeros.
 *             Not defined by default, will overwrite `SRC_BUFFER_INIT_BYTE` when defined.
 *             Format: {0xBB, 0xBB, 0xBB, ...}
 *
 */

#include "hal.h"
#include "hal/stm32f4-hal.h"
#include "simpleserial/simpleserial.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define setup_trigger() inline_gpio_mode_setup(GPIOA, GPIO_MODE_OUTPUT, GPIO_PUPD_PULLDOWN, GPIO12)
#define set_trigger() inline_gpio_set(GPIOA, GPIO12)
#define clear_trigger() inline_gpio_clear(GPIOA, GPIO12)

// +-----------------------------------------+
// |             CONFIG VARIABLES            |
// +-----------------------------------------+
// TODO: allow for storage configuration: heap (-> malloc) / stack (-> array)
#define BUFFER_SIZE 68
#define SRC_BUFFER_INIT_BYTE 0xAA
#define TARGET_BUFFER_INIT_BYTE 0xBB
// #define SRC_BUFFER_INIT_SEQUENCE {0xAA, 0xAA}
// #define TARGET_BUFFER_INIT_SEQUENCE {0xBB, 0xBB}

int main(void)
{
    platform_init();
    init_uart();
    setup_trigger(); // using custom hal
    send_reset_sequence();
    volatile unsigned int count = 500;
    char uart_ret;

    // Arrays holding initalization data for buffers
    #ifdef SRC_BUFFER_INIT_SEQUENCE
    const char src_init[BUFFER_SIZE] = SRC_BUFFER_INIT_SEQUENCE;
    #endif
    #ifdef TARGET_BUFFER_INIT_SEQUENCE
    const char target_init[BUFFER_SIZE] = TARGET_BUFFER_INIT_SEQUENCE;
    #endif

    char src[BUFFER_SIZE];
    char target[BUFFER_SIZE];

    while (1)
    {
        uint8_t cmd;
        size_t dummy_len;
        int res = readpacket(&cmd, NULL, &dummy_len); // Read start signal
        if (res == 0 && cmd == 's')
        {
            send_ack(cmd); // Acknowledge start signal

            // Initalize src buffer
            #ifdef SRC_BUFFER_INIT_SEQUENCE
            memcpy(src, src_init, BUFFER_SIZE);
            #else
            memset(src, SRC_BUFFER_INIT_BYTE, sizeof(src)); // Initialize source buffer
            #endif

            // Initalize target buffer
            #ifdef TARGET_BUFFER_INIT_SEQUENCE
            memcpy(target, target_init, BUFFER_SIZE);
            #else
            memset(target, TARGET_BUFFER_INIT_BYTE, sizeof(target)); // Initialize target buffer
            #endif

            set_trigger();

            memcpy(target, src, sizeof(src)); // Attacked code

            clear_trigger();

            if (memcmp(src, target, sizeof(src)) != 0) {
                sendpacket('f', target, sizeof(target)); // Fault packet
            } else {
                sendpacket('e', NULL, 0); // End signal
            }
        }
    }
}
