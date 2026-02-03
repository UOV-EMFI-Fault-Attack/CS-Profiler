#include "hal.h"
#include "hal/stm32f4-hal.h"
#include "simpleserial.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/**
 * @brief Send a raw buffer of bytes sequentially via putch().
 *
 * @param buf Pointer to the byte buffer.
 * @param len Number of bytes to send.
 */
void send_buf(const uint8_t *buf, size_t len)
{
    if (!buf || len == 0)
        return;

    for (size_t i = 0; i < len; i++)
    {
        putch(buf[i]);
    }
}

/**
 * @brief Send a null terminated string via putch (not including the terminator).
 *
 * @param in Pointer to the byte buffer.
 */
void send_str(const char* in)
{
    const char* cur = in;
    while (*cur) {
        putch(*cur);
        cur += 1;
    }
}

/**
 * @brief Calculate 8-bit CRC for a given buffer using polynomial 0x4D.
 *
 * This implements a bitwise CRC calculation. The CRC is initialized to 0x00.
 *
 * @param buf Pointer to input data buffer.
 * @param len Length of the input buffer.
 * @return Calculated 8-bit CRC value.
 */
uint8_t calc_crc(const uint8_t *buf, size_t len)
{
    uint8_t crc = 0x00;
    for (size_t i = 0; i < len; ++i)
    {
        crc ^= buf[i];
        for (uint8_t j = 0; j < 8; ++j)
        {
            if (crc & 0x80)
                crc = (crc << 1) ^ 0x4D;
            else
                crc <<= 1;
        }
    }
    return crc;
}

/**
 * @brief Encode a buffer using Consistent Overhead Byte Stuffing (COBS).
 *
 * This function handles blocks up to 254 bytes. A new block is automatically
 * created whenever the FRAME_BYTE is detected or the maximum block length is reached.
 *
 * @param buf Pointer to input buffer to encode.
 * @param len Length of the input buffer.
 * @param out Pointer to output buffer; must be preallocated with sufficient size.
 * @return Number of bytes written to the output buffer.
 */
size_t cobs_stuff_data(const uint8_t *buf, size_t len, uint8_t *out)
{
    if (!buf || len == 0)
        return 0;

    size_t out_index = 1; // first code byte placeholder
    size_t code_index = 0;
    uint8_t code = 1;

    for (size_t i = 0; i < len; ++i)
    {
        uint8_t b = buf[i];
        if (b == FRAME_BYTE || code == 0xFF)
        {
            out[code_index] = code;
            code_index = out_index;
            out[out_index++] = 0; // placeholder for next code byte
            code = 1;
        }
        if (b != FRAME_BYTE)
        {
            out[out_index++] = b;
            code++;
        }
    }
    out[code_index] = code; // finalize last block
    return out_index;       // return encoded length
}

/**
 * @brief Decode a COBS-encoded buffer.
 *
 * This function works with blocks up to 254 bytes and optional trailing zeros.
 * Invalid COBS sequences will print an error message to stderr and return 0.
 *
 * @param buf Pointer to input COBS-encoded buffer.
 * @param len Length of the encoded buffer.
 * @param out Pointer to output buffer; must be preallocated with sufficient size.
 * @return Number of bytes written to the output buffer.
 */
size_t cobs_unstuff_data(const uint8_t *buf, size_t len, uint8_t *out)
{
    if (!buf || len == 0)
        return 0;

    size_t in_index = 0;
    size_t out_index = 0;

    while (in_index < len)
    {
        uint8_t code = buf[in_index++];
        if (code == 0)
        {
            fprintf(stderr, "Invalid COBS: code byte cannot be 0\n");
            return 0;
        }

        size_t end = in_index + code - 1;
        if (end > len)
        {
            fprintf(stderr, "Invalid COBS: block extends past end of buffer\n");
            return 0;
        }

        for (size_t i = in_index; i < end; ++i)
            out[out_index++] = buf[i];

        in_index = end;

        if (code < 0xFF && in_index < len)
            out[out_index++] = FRAME_BYTE;
    }
    return out_index; // length of unstuffed data
}

/**
 * @brief Calculate maximum COBS-encoded buffer length for a given input length.
 *
 * Worst case: Each block of 254 bytes adds one code byte. One extra byte is added at the start.
 *
 * @param input_len Length of the original data buffer.
 * @return Maximum required encoded buffer length.
 */
size_t get_max_encode_len(size_t input_len)
{
    return input_len + (input_len / 254) + 1;
}

/**
 * @brief Calculate maximum decoded buffer length for a given encoded length.
 *
 * In the worst case, every code byte encodes a single data byte, so decoded length
 * is less than or equal to the encoded length.
 *
 * @param encoded_len Length of the encoded buffer.
 * @return Maximum possible decoded buffer length.
 */
size_t get_max_decode_len(size_t encoded_len)
{
    return encoded_len;
}

/**
 * @brief Reads from the input until a specified byte sequence is seen.
 *
 * @param seq Pointer to the byte sequence to match.
 * @param seq_len Length of the byte sequence.
 * @param out_len Pointer to store length of returned buffer (including the matched sequence).
 * @return Dynamically allocated buffer containing the read data including the sequence
 *
 * Example Usage:
 *     uint8_t sequence[] = {0x00};
 *     size_t buf_len;
 *     uint8_t *buf = read_until_sequence(sequence, 1, &buf_len);
 */
uint8_t *read_until_sequence(const uint8_t *seq, size_t seq_len, size_t *out_len)
{
    if (!seq || seq_len == 0 || !out_len) return NULL;

    size_t buf_size = 64;
    size_t pos = 0;
    uint8_t *buf = malloc(buf_size);
    if (!buf) return NULL;

    while (1)
    {
        uint8_t byte;
        byte = getch();

        if (pos >= buf_size) {
            size_t new_size = buf_size + 64; // grow buffer
            uint8_t *new_buf = realloc(buf, new_size);
            if (!new_buf) {
                free(buf);
                return NULL; // allocation failure
            }
            buf = new_buf;
            buf_size = new_size;
        }

        buf[pos] = byte;
        pos++;

        // Check if the last seq_len bytes match the sequence
        if (pos >= seq_len && memcmp(&buf[pos - seq_len], seq, seq_len) == 0) {
            break; // matched the sequence
        }
    }

    *out_len = pos;
    return buf;
}


/**
 * @brief Reads bytes from input until a terminator (FRAME_BYTE) is encountered.
 *
 * This function repeatedly calls `getch()` to read one byte at a time and
 * stores the bytes into a dynamically allocated buffer. The buffer grows
 * automatically in chunks of 64 bytes if more space is needed. The reading
 * process stops when a byte equal to FRAME_BYTE is received. The buffer returned
 * includes the terminator byte at the end.
 *
 * @param[out] len Pointer to a size_t variable where the total number of bytes
 *                 read (including the terminator) will be stored.
 *
 * @return A pointer to a dynamically allocated buffer containing the received
 *         data, or NULL if memory allocation fails. The caller is responsible
 *         for freeing the buffer using `free()`.
 *
 * @note This function blocks indefinitely until the terminator is read.
 *       Consider adding a timeout if the input may never send a terminator.
 */
uint8_t *read_until_terminator(size_t *len)
{
    size_t buf_size = 64;
    size_t pos = 0;
    uint8_t *buf = malloc(buf_size);

    if (!buf) return NULL;
    if (!len) {
        free(buf);
        return NULL;
    }

    while (1)
    {
        uint8_t byte;
        byte = getch();

        if (pos >= buf_size) {
            size_t new_size = buf_size + 64;
            uint8_t *new_buf = realloc(buf, new_size);
            if (!new_buf) {
                free(buf);
                return NULL;
            }
            buf = new_buf;
            buf_size = new_size;
        }

        buf[pos] = byte;
        pos++;

        if (byte == FRAME_BYTE) break; // terminator
    }

    *len = pos;
    return buf;
}

/**
 * send_reset_sequence
 *
 * Sends the predefined reset sequence to the output.
 * The sequence is equivalent to: [0, 0, 0, 114, 0, 0, 0]
 * where 114 corresponds to the ASCII character 'r'.
 */
void send_reset_sequence()
{
    uint8_t reset_sequence[] = {0, 0, 0, 114, 0, 0, 0};
    send_buf(reset_sequence, sizeof(reset_sequence));
}

/**
 * @brief Send an ACK packet for a given command.
 *
 * The ACK format is simply [command, FRAME_BYTE].
 *
 * @param command Command byte (0–255) to acknowledge.
 */

void send_ack(uint8_t command)
{
    uint8_t ack[2];
    ack[0] = command;
    ack[1] = FRAME_BYTE;
    send_buf(ack, sizeof(ack));
}

/**
 * @brief Wait for an ACK packet for a given command.
 *
 * Reads next command (until next terminator). And checks if it is an ACK packet for a
 * given command.
 *
 * The ACK packet format is:
 *    [command, FRAME_BYTE]
 *
 * @param cmd The command byte we expect to be acknowledged.
 * @return 0 on success, -1 on error or mismatch.
 */
int wait_ack(uint8_t cmd)
{
    size_t buf_len = 0;

    // Read until we hit a terminator (FRAME_BYTE)
    uint8_t *buf = read_until_terminator(&buf_len);
    if (!buf) {
        return -1; // allocation or read failure
    }

    if (buf_len != 2) {
        // ACK must be exactly [cmd, terminator]
        free(buf);
        return -1;
    }

    // Strip terminator
    uint8_t received_cmd = buf[0];
    free(buf);

    if (received_cmd != cmd)
        return -1;

    return 0;
}

/**
 * @brief Send a SimpleSerial packet.
 *
 * @param cmd Command byte (0–255).
 * @param data Pointer to optional data buffer (can be NULL).
 * @param data_len Length of data (0 if none).
 * @return 0 on success, -1 on error.
 */
int sendpacket(uint8_t cmd, const uint8_t *data, size_t data_len)
{
    if (!data) data_len = 0;
    // No data: just [cmd, terminator]
    if (data_len == 0)
    {
        uint8_t buf[2];
        buf[0] = cmd;
        buf[1] = FRAME_BYTE; // terminator
        send_buf(buf, sizeof(buf));
        return 0;
    }

    // Send cmd byte
    send_buf(&cmd, 1);

    // Compute CRC
    uint8_t crc = calc_crc(data, data_len);

    // COBS stuffing in stream mode (directly send out blocks after computing)
    // -> more efficient than using cobs_stuff_data() and allocating large buffers
    // especially requires less memory on stack

    uint8_t cobs_block[255]; // Max block length is 255 (0xFF)
    // block: [code byte, data[i], data[i+1], ...]

    size_t code_index = 0; // code byte index
    uint8_t code = 1; // code (block length)

    for (size_t i = 0; i < data_len + 1; ++i) // +1 for CRC
    {
        uint8_t b;
        if (i < data_len) {
            b = data[i];
        }
        else {
            b = crc;
        }

        // Block terminated by frame byte or by reaching max block length
        if (b == FRAME_BYTE || code == 0xFF)
        {
            // Set code (block length)
            cobs_block[code_index] = code;

            // Send block
            send_buf(cobs_block, code);

            // Reset counters
            code_index = 0;
            code = 1; // only code byte
        }
        // Normal byte (non - FRAME_BYTE) -> append to cobs_block
        if (b != FRAME_BYTE)
        {
            cobs_block[code] = b;
            code++;
        }
    }
    cobs_block[code_index] = code; // Finalize last block

    // Send last block
    send_buf(cobs_block, code);

    // Send terminator
    uint8_t terminator = FRAME_BYTE;
    send_buf(&terminator, 1);

    return 0;
}

/**
 * @brief Reads and decodes a SimpleSerial packet.
 *
 * @param cmd Pointer to store received command byte.
 * @param data Pointer to store dynamically allocated data buffer (must be free'd by caller).
 * @param data_len Pointer to store length of received data.
 * @return Number of data bytes on success, 0 for empty packet, -1 on error.
 *
 * Example usage:
 *    uint8_t cmd;
 *    uint8_t *data;
 *    size_t data_len;
 *    int res = readpacket(&cmd, &data, &data_len);
 *    for (size_t i = 0; i < data_len; i++) {
 *      printf("%02X ", data[i]);
 *    }
 *
 * Or for simple packet (without data):
 *    uint8_t cmd;
 *      size_t dummy_len;
 *      int res = readpacket(&cmd, NULL, &dummy_len);
 */
int readpacket(uint8_t *cmd, uint8_t **data, size_t *data_len)
{
    if (!cmd) {
        return -1;
    }
    // Read full packet including terminator
    size_t buf_len;
    uint8_t *buf = read_until_terminator(&buf_len);

    if (!buf) return -1; // read error

    if (buf_len == 0) {
        free(buf);
        return -1;
    }

    buf_len--; // Strip terminator (FRAME_BYTE)

    if (buf_len == 1) {
        // Simple packet: only cmd, no data
        *cmd = buf[0];
        free(buf);
        return 0;
    }

    if (!data || !data_len) {
        return -1;
    }

    *cmd = buf[0];

    // Packet with data
    size_t cobs_block_len = buf_len - 1; // exclude cmd
    size_t max_decode_len = get_max_decode_len(cobs_block_len);
    uint8_t *decoded = malloc(max_decode_len);
    if (!decoded) {
        free(buf);
        return -1;
    }

    size_t decoded_len = cobs_unstuff_data(&buf[1], cobs_block_len, decoded);
    free(buf);

    if (decoded_len > max_decode_len || decoded_len == 0) {
        free(decoded);
        return -1; // decode error or length mismatch
    }

    // Separate CRC
    uint8_t crc = decoded[decoded_len - 1];
    *data_len = decoded_len - 1;

    // Validate CRC
    if (calc_crc(decoded, *data_len) != crc) {
        free(decoded);
        return -1;
    }

    // Return decoded data to caller
    *data = decoded;

    return 0;
}

