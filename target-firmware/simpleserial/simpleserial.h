#ifndef TARGET_SIMPLESERIAL_H
#define TARGET_SIMPLESERIAL_H

#include <stdint.h>
#include <stddef.h>

#define FRAME_BYTE 0x00


uint8_t calc_crc(const uint8_t *buf, size_t len);

/* ---------------- COBS ---------------- */
size_t get_max_encode_len(size_t input_len);
size_t get_max_decode_len(size_t encoded_len);
size_t cobs_stuff_data(const uint8_t *buf, size_t len, uint8_t *out);
size_t cobs_unstuff_data(const uint8_t *buf, size_t len, uint8_t *out);

uint8_t *read_until_sequence(const uint8_t *seq, size_t seq_len, size_t *out_len);
uint8_t *read_until_terminator(size_t *len);

int sendpacket(uint8_t cmd, const uint8_t *data, size_t data_len);
void send_reset_sequence();
void send_str(const char* in);
void send_ack(uint8_t command);
int wait_ack(uint8_t cmd);

int readpacket(uint8_t *cmd, uint8_t **data, size_t *data_len);

#endif // TARGET_SIMPLESERIAL_H
