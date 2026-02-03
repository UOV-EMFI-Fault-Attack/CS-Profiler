from .simpleserial_readers.cwlite import SimpleSerial_ChipWhispererLite
from collections import OrderedDict, deque
import time
import inspect
import ctypes

def dict_to_str(input_dict: dict, indent=""):
    """
    Recursively converts a dictionary into a nicely formatted string for display.

    Each key-value pair is printed on its own line, with keys left-aligned
    to the maximum width of all keys at the current dictionary level.
    Nested dictionaries are indented for readability.

    Example:
        input_dict = {
            'name': 'Device1',
            'status': 'OK',
            'metrics': {
                'temp': 42,
                'voltage': 3.3
            }
        }
        print(dict_to_str(input_dict))

        Output:
            name    = Device1
            status  = OK
            metrics =
                temp    = 42
                voltage = 3.3

    Args:
        input_dict (dict): The dictionary to convert. Keys should be strings
            (or convertible to strings) and values can be any type, including
            nested dictionaries.
        indent (str, optional): String used for indentation of nested dictionaries.
            Defaults to "".

    Returns:
        str: A formatted string representation of the dictionary, suitable for
            printing to the console.
    """
    # Find minimum width that fits all names
    min_width = 0
    for n in input_dict:
        min_width = max(min_width, len(str(n)))

    # Build string
    ret = ""
    for n in input_dict:
        if isinstance(input_dict[n], dict):
            ret += indent + str(n) + ' = '
            ret += '\n' + dict_to_str(input_dict[n], indent+"    ")
        else:
            ret += indent + str(n).ljust(min_width) + ' = '
            ret += str(input_dict[n]) + '\n'

    return ret

class PacketDataStruct(ctypes.Structure):
    """
    Ctypes structure with integrated as_dict() method. Used to parse PacketData as individual values.

    - as_dict(): Returns structure as dict
            - Byte arrays (`c_uint8 * N | c_byte * N`) are converted to bytes()
            - Char arrays (`c_char * N`) are converted to strings.
            - Others are returned as-is.

    Example Usage:
        ```
        class PacketData(PacketDataStruct):
        _fields_ = [
            ("target_buffer", ctypes.c_uint8 * 68), # 68 bytes memcpy target buffer
            # ("variable_1", ctypes.c_uint32),       # 4 bytes (unsigned int)
            # ("variable_3", ctypes.c_uint8 * 34),  # 34 bytes (byte buffer)
            # ("variable_4", ctypes.c_char * 34),   # 34 bytes (char strings)
        ]

        data = bytes([...])
        packetData = PacketData()
        struct_size = ctypes.sizeof(packetData)
        # Ensure received data is long enough
        if len(data) < struct_size:
            raise ValueError(f"Data too short (expected {struct_size} bytes, got {len(data)})")
        # Populate structure from buffer
        parsed = packetData.from_buffer_copy(data)
        ```
    """
    _pack_ = 1 # no padding between fields

    def as_dict(self):
        result = {}
        # Iterate over all fields of the ctypes struct
        for field_name, field_type in self._fields_:
            value = getattr(self, field_name)
            # Handle byte arrays (e.g. c_uint8 * N) -> make sure that the dict values are json serializable for logging
            if issubclass(field_type, ctypes.Array):
                # Check element type
                elem_type = field_type._type_
                if elem_type in (ctypes.c_uint8, ctypes.c_byte):
                    # Byte array:
                    result[field_name] = bytes(value)
                elif elem_type == ctypes.c_char:
                    # String
                    result[field_name] = bytes(value)
                else:
                    # Fallback: convert array elements to list
                    result[field_name] = list(value)
            else:
                # Primitive types (int, uint, etc)
                result[field_name] = value

        return result

class SimpleSerial_Err:
    OK = 0
    ERR_CMD = 1
    ERR_CRC = 2
    ERR_TIMEOUT = 3
    ERR_LEN = 4
    ERR_FRAME_BYTE = 5

class TargetSerial:
    """
    Simplify serial communication with target via different devices.

    Functionality:
        - send(), read():       Direct sending and reading of data.
        - peek():               Read data without removing from input buffer, so it can later be read again with `read()`.
        - read_until():         Read until a specific sequence is received. (used by `read_until_reset()`)
        - wait_for_seaquence(): Block until a specific sequence is received. (used by `wait_ack()`)
        - read_packet():        Read a packet (with or without data)
        - send_packet():        Send a packet (with or without data)

    Packets are composed of a command, optional data (including crc) and a terminator frame_byte (0x00).
    The command can be any single byte value except 0x00 since that is the frame_byte.

    Simple packets (sometimes also referred to as "signals") include only the command and terminator: [cmd, 0x00]
    Packets with data have include singe byte CRC appended to the data (poly=0x4D): [cmd, COBS([data, crc]) 0x00]
        The data and CRC are COBS encoded with `_cobs_stuff_data()` to escape any occurences of the frame_byte.

    A packet can be acknowledged with it's command: [cmd, 0x00]
    An acknowledged not bound to a specific command is defined as: [0x00]

    Acknowleging a packet is not required and not done automatically.
    """
    _frame_byte = bytes([0])
    _reset_sequence = bytes([0, 0, 0, 114, 0, 0, 0])
    _simple_ack = bytes([0])
    # _command_ack = bytes[<command_byte>, 0x00]

    def __init__(self, driver, interface=None, baud=38400, stopbits=1, parity="none", flush_on_err=True):
        """
        Initialize the serial connection wrapper.

        This constructor sets up a serial communication interface using the
        specified driver. Some serial drivers require passing an interface
        for example `cw.scope` for `SimpleSerial_ChipWhispererLite` driver.

        Args:
            driver (subclass(SimpleSerialTemplate)): The serial driver class to use.
            interface (object, optional): The interface object required by some
                drivers (e.g., `cw.scope` for ChipWhisperer Lite). Defaults to None.
            baud (int, optional): Baud rate for the serial connection. Defaults to 38400.
            stopbits (int, optional): Number of stop bits. Defaults to 1.
            parity (str, optional): Parity setting. Can be `"none"`, `"even"`, or `"odd"`.
                Defaults to `"none"`.
            flush_on_err (bool, optional): If True, flush the serial buffers on error.
                Defaults to True.

        Raises:
            ValueError: If `driver` requires the interface parameter but it is not provided.
        """

        #TODO: add additional drivers (simple tty) -> make driver not optional
        #TODO: add support for additional hardware layers (, CAN, I2C, SPI etc.) -> remove baud, stopbits, parity stuff from this class
            # -> Add driver.init() function that will get all kwargs passed to it

        self.ser = driver()
        self.interface = interface
        self.connect()

        self.baud=baud
        self.stobits=stopbits
        self.parity=parity

        self._flush_on_err = flush_on_err


    def connect(self):
        """
        Connect (calls driver.con() method with self.interface)

        Raises:
            ValueError: If `driver` requires the interface parameter but self.interface is None.
        """
        con_num_mandatory_params = sum(p.default is inspect.Parameter.empty
                for p in inspect.signature(self.ser.con).parameters.values()
                if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                            inspect.Parameter.POSITIONAL_OR_KEYWORD))

        if not self.interface and con_num_mandatory_params > 0:
            raise ValueError(f"SimpleSerial driver {type(self.ser)} con() method requires the interface parameter.")

        self.ser.con(self.interface)
        self.flush()

    def flush_on_error(self):
        """
        Function called when an error occured (e.g. timeout in wait_for_sequence) and flush_on_err is set to true in __init__

        Removes all data from the serial buffer.
        """
        if self._flush_on_err:
            self.flush()

    @staticmethod
    def _calc_crc(buf):
        """
        Calculate CRC (0x4D) for buf

        Raises:
            RuntimeError: If CRC calculation failed.
        """
        crc = 0x00
        try:
            for b in buf:
                crc ^= b
                for _ in range(8):
                    if crc & 0x80:
                        crc = (crc << 1) ^ 0x4D
                        crc &= 0xFF
                    else:
                        crc <<= 1
                        crc &= 0xFF
        except Exception as e:
            raise RuntimeError(f"CRC calculation failed for buffer {buf}") from e

        return crc

    @staticmethod
    def _cobs_stuff_data(buf: bytes, frame_byte: int = 0x00) -> bytes:
        """
        Encode a byte buffer using COBS (Consistent Overhead Byte Stuffing).

        This function transforms the input buffer `buf` into a COBS-encoded
        byte sequence, suitable for framing in serial protocols. It handles
        blocks larger than 254 bytes by automatically starting new blocks.

        Encoding rules:
            - When `frame_byte` (default 0x00) is detected in the input, a new block is created.
            - Each block begins with a code byte, indicating the block length + 1.
            - No `frame_byte` is stored in the output; it is used only to split blocks.
            - A new block is also created automatically if the block length reaches 0xFF.
            - The output is returned as an immutable `bytes` object.

        Args:
            buf (bytes): The input byte buffer to encode.
            frame_byte (int, optional): The byte value to treat as a frame separator.
                Defaults to 0x00.

        Returns:
            bytes: The COBS-encoded byte sequence.

        Example:
            >>> data = b'\x11\x00\x22'
            >>> TargetSerial._cobs_stuff_data(data)
            b'\x02\x11\x02\x22'
        """

        if not buf:
            return b""

        out = bytearray([0])  # placeholder for first code byte
        code = 1  # code byte (length of block +1)
        code_index = 0  # index of last code byte

        for b in buf:
            # frame_byte is detected or block length reached 0xFF
            if b == frame_byte or code == 0xFF:
                # close current block
                out[code_index] = code
                code_index = len(out)
                out.append(0)  # append new placeholder for next code
                code = 1
            if b != frame_byte:
                out.append(b)
                code += 1

        out[code_index] = code  # finalize last block
        return bytes(out)  # return immutable bytes obect

    @staticmethod
    def _cobs_unstuff_data(buf: bytes, frame_byte: int = 0x00) -> bytes:
        """
        Decode a COBS-encoded byte buffer.

        Reverses the transformation applied by `_cobs_stuff_data`. Handles
        blocks up to 254 bytes and properly restores inserted frame bytes
        when decoding.

        Decoding rules:
            - Each block begins with a code byte, indicating how many bytes to read.
            - If `code < 0xFF`, a `frame_byte` is appended after the block (unless at the end).
            - Blocks are copied sequentially to reconstruct the original data.

        Args:
            buf (bytes): The COBS-encoded input buffer.
            frame_byte (int, optional): The byte used as frame separator in the original encoding.
                Defaults to 0x00.

        Raises:
            ValueError: If a code byte is 0, or if a block extends beyond the end of the buffer.

        Returns:
            bytes: The decoded original byte sequence.

        Example:
            >>> encoded = b'\x02\x11\x02\x22'
            >>> TargetSerial._cobs_unstuff_data(encoded)
            b'\x11\x00\x22'
        """

        if not buf:
            return b""

        out = bytearray()
        index = 0
        length = len(buf)

        while index < length:
            code = buf[index]
            if code == 0:
                raise ValueError("Invalid COBS: code byte cannot be 0")
            index += 1  # move to the data part

            # Calculate how many bytes to copy
            end = index + code - 1
            if end > length:
                raise ValueError("Invalid COBS: block extends past end of buffer")

            # Copy the block bytes
            out.extend(buf[index:end])
            index = end

            # Add a zero only if code < 0xFF and we’re not at the end
            if code < 0xFF and index < length:
                out.append(frame_byte)

        return bytes(out)  # return immutable bytes obect

    @staticmethod
    def _verify_crc(buf: bytes) -> bool:
        """
        Verify CRC for a buffer.

        Args:
            buf (bytes): Buffer for CRC calculation

        Returns:
            bool: True if CRC matches, False otherwise.
        """
        if len(buf) < 2:
            # Not enough data to have CRC
            return False

        data = buf[:-1]  # All bytes except the last one (CRC)
        received_crc = buf[-1]

        calculated_crc = TargetSerial._calc_crc(data)
        return calculated_crc == received_crc

    @staticmethod
    def type_convert_cmd(cmd) -> int:
        """
        Convert some different types to a command (single byte integer (0-255)).

        Args:
            cmd (int | str): The command to convert.
            If a string, only the first character is used.

        Raises:
            TypeError: If cmd is not int or str.
            ValueError: If cmd is out of the valid byte range (0-255).

        Returns:
            int: Command as a single byte integer.
        """
        # Convert str to int (use first character)
        if isinstance(cmd, str):
            if len(cmd) == 0:
                raise ValueError("Command string cannot be empty")
            cmd = ord(cmd[0])

        # Verify type
        if not isinstance(cmd, int):
            raise TypeError(f"Unsupported command type: {type(cmd)}")

        # Verify value range
        if not (0 <= cmd <= 255):
            raise ValueError(f"Command `{cmd}` out of byte range (0-255)")

        return cmd

    @staticmethod
    def type_convert_data(data) -> bytes:
        """
        Convert various input types to bytes.

        Supported types:
        - list or tuple of ints -> bytes
        - str -> ASCII-encoded bytes
        - int (0-255) -> single byte
        - bytes or bytearray -> bytes

        Args:
            data (list[ints] | str | int | bytes | bytearray): Input data

        Raises:
            ValueError: If data contains integers outside of single byte range (0-255)
            TypeError: If data is of unsupported type.

        Returns:
            bytes: Converted data
        """
        # Type convert data
        if isinstance(data, list) or isinstance(data, tuple):
            data = bytearray(data)
        elif isinstance(data, str):
            data = data.encode("ascii")
        elif isinstance(data, int):
            if not (0 <= data <= 255):
                raise ValueError(f"Integer out of byte range: {data}")
            data = bytes([data])

        # Verify data type
        elif not isinstance(data, (bytes, bytearray)):
            raise TypeError(f"Unsupported data type: {type(data)}")

        return bytes(data)

    @staticmethod
    def parse_packet_data_struct(data: bytes | None, struct_fields: list) -> dict:
        """
        Parse packet data using a ctypes filed list.

        A PacketDataStruct object is created with `struct_fields`.
        The data bytes are parsed and then converted to dict.

        Args:
            data (bytes): Data to be parsed.
            struct_fields (list): Ctypes field list used for parsing

        Raises:
            ValueError: If data is too short to fill length of struct defined by `struct_fields`

        Returns:
            dict: Data parsed as dict (using PacketDataStruct.as_dict()).

        Example Usage:
            ```
            fields = [
                ("target_buffer", ctypes.c_uint8 * 68), # 68 bytes memcpy target buffer
                ("variable_1", ctypes.c_uint32),        # 4 bytes (unsigned int)
                ("variable_3", ctypes.c_uint8 * 34),    # 34 bytes (byte buffer)
                ("variable_4", ctypes.c_char * 34),     # 34 bytes (char strings)
            ]
            ```
        """
        class PacketData(PacketDataStruct):
            _fields_ = struct_fields

        struct_size = ctypes.sizeof(PacketData)

        # Ensure received data is long enough
        if len(data) < struct_size:
            raise ValueError(f"Data too short (expected {struct_size} bytes, got {len(data)})")

        # Populate structure from buffer
        parsed = PacketData.from_buffer_copy(data)
        return parsed.as_dict()


    def send_packet(self, cmd, data=None, timeout=0):
        """
        Send a SimpleSerial packet to the target device.

        Converts the command and optional data to the appropriate types,
        builds a packet (with optional COBS encoding, CRC, and terminator),
        and writes it to the target.

        Args:
            cmd (int or str): Command to send. Can be an integer (0-255) or a single-character string.
            data (bytes, bytearray, str, list, tuple, optional): Optional payload data to send.
                Supported types include bytes, bytearray, str (ASCII), list/tuple of integers.
                Defaults to None.
            timeout (int, optional): Timeout in milliseconds for the write operation. Defaults to 0.

        Raises:
            TypeError: If `cmd` or `data` is of an unsupported type.
            ValueError: If `cmd` is out of the byte range (0-255) or if data conversion fails.
        """
        cmd = self.type_convert_cmd(cmd)
        if data:
            data = self.type_convert_data(data)

        # Packet without data (just send command and terminator)
        if not data:
            buf = bytearray([cmd, 0])
            self.write(buf, timeout)
            return

        # Packet with data (send encoded packet)
        else:
            # Compute CRC over data only
            crc = self._calc_crc(data)

            # Build block = data + crc
            block = data + bytes([crc])

            # COBS encode
            encoded = self._cobs_stuff_data(block)

            # Final packet: cmd + encoded + terminator
            pkt = bytearray([cmd])
            pkt.extend(encoded)
            pkt.append(0x00)

            # Send
            self.write(buf, timeout)

    def send_ack(self, cmd, timeout=0):
        self.send_packet(cmd, timeout)

    def read(self, num_bytes = 0, timeout = 250) -> bytes:
        """ Reads data from the target over serial.

        Args:
            num_bytes (int, optional): Number of bytes to read. If 0, read all
                data available. Defaults to 0.
            timeout (int, optional): How long in ms to wait before returning.
                If 0, block until data received. Defaults to 250.

        Returns:
            bytes: received data
        """
        if num_bytes == 0:
            num_bytes = self.ser.inWaiting()
        if timeout == 0:
            timeout = 1000000000000
        return self.ser.read_bytes(num_bytes, timeout)

    def peek(self, num_bytes : int, timeout=250) -> bytes:
        """
        Reads num_bytes without deleting them from the read buffer.

        Args:
            num_bytes (int: num_bytes (int, optional): Number of bytes to read.
            timeout (int, optional): How long in ms to wait before returning.
                If 0, block until data received. Defaults to 250.

        Returns:
            bytes: received data
        """
        self.ser.peek_bytes(num_bytes, timeout)

    def read_until(self, sequence, timeout=250) -> bytes:
        """Read data until a specific sequence is encountered or timeout is reached.

        Args:
            sequence (bytes, str, list): The byte sequence to read until.
            timeout (int, optional): How long to wait in ms. Defaults to 250.

        Returns:
            bytes: All data read up to and including the sequence.
        """
        sequence = self.type_convert_data(sequence)

        result = bytearray()
        seq_len = len(sequence)
        buffer = deque(maxlen=seq_len)  # keeps only last seq_len bytes
        end_time = time.time() + (timeout / 1000.0)

        while time.time() < end_time:
            byte_read = self.ser.read_bytes(1, timeout=10)
            if byte_read:
                b = byte_read[0]
                result.append(b)
                buffer.append(b)

                # Always check only the last seq_len bytes
                if len(buffer) == seq_len and bytes(buffer) == bytes(sequence):
                    break

        return bytes(result)

    def read_until_reset(self, timeout=250):
        """
        Read until reset sequence is encountered.


        Args:
            timeout (int, optional): _description_. Defaults to 500.

        Returns:
            bytes: All data read up to and including the sequence.
            SimpleSerial_Err (int): SimpleSerial_Err.ERR_TIMEOUT (=3) when timeout is reached
        """
        received_data = self.read_until(self._reset_sequence, timeout)
        if received_data.endswith(self._reset_sequence):
            return 0
        else:
            raise TimeoutError(f"read_until_reset timed out. Received data: {received_data}")

    def read_packet(self, timeout=250):
        """
        Receive and decode a SimpleSerial packet.

        This method reads data from the serial interface, decodes it according
        to the SimpleSerial protocol, and verifies its CRC. Returns the command
        byte and payload as a tuple.

        Args:
            timeout (int, optional): Timeout in milliseconds to wait for a complete
                packet. Defaults to 250.

        Returns:
            tuple: `(cmd, data)` where:
                - `cmd`  (int): Command byte
                - `data` (bytes): Payload of the packet

        Raises:
            TimeoutError: If no complete packet is received before the timeout.
            ValueError: If decoding fails or the CRC check fails.

        Example:
            >>> cmd, data = obj.read_packet(timeout=500)
            >>> print(cmd, data)
        """
        buf = bytearray()
        buf = self.read_until(self._frame_byte, timeout)

        if not buf.endswith(self._frame_byte):
            raise TimeoutError("receive_packet: Timeout waiting for packet terminator")

        # Strip terminator
        buf = buf[:-1]

        # Packet without data
        if len(buf) == 1:
            cmd = buf[0]
            data = None
            return (cmd, data)

        # Packet with data
        else:
            cmd = buf[0]

            # Extract COBS-encoded block
            encoded = buf[1:]
            decoded = self._cobs_unstuff_data(encoded)
            if len(decoded) < 1:
                raise ValueError("read_packet: decode failed")

            # Split data + CRC
            data, crc = decoded[:-1], decoded[-1]

            # Verify CRC
            if self._calc_crc(data) != crc:
                raise ValueError("read_packet: CRC mismatch")

            return (cmd, data)

    def wait_for_sequence(self, sequence: bytes, timeout=250):
        """
        Waits for specific sequence from the target for timeout ms

        Args:
            sequence (bytes): Sequence of bytes that should be waited for.
            timeout (int, optional): Time to wait for an ack in ms. If 0, block
                until ACK is received. Defaults to 500.

        Returns:
            SimpleSerial_Err.OK (0): If sequence was received
            SimpleSerial_Err.ERR_TIMEOUT (3): If timeout is reached
            SimpleSerial_Err.ERR_CMD (1): If wrong data was received
        """
        sequence = self.type_convert_data(sequence)

        x = self.read(len(sequence), timeout=timeout)
        if x == sequence:
            return SimpleSerial_Err.OK
        elif x is None:
            self.flush_on_error()
            return SimpleSerial_Err.ERR_TIMEOUT
        else:
            self.flush_on_error()
            return SimpleSerial_Err.ERR_CMD

    def wait_ack(self, command=None, timeout=250):
        """
        Waits for an ack/error packet from the target for timeout ms

        Args:
            command (int, optional): Command that the ack should belong to. Defaults to None.
            timeout (int, optional): Time to wait for an ack in ms. If 0, block
                until ACK is received. Defaults to 500.

        Returns:
            SimpleSerial_Err.OK (0): If ACK sequence was received
            SimpleSerial_Err.ERR_TIMEOUT (3): If read timed out
            SimpleSerial_Err.ERR_CMD (1): If wrong data was received
        """

        if command:
            command = self.type_convert_cmd(command)
            ack_sequence = bytes([command, 0])
        else:
            ack_sequence = bytes([0])

        return self.wait_for_sequence(ack_sequence, timeout)

    def write(self, data, timeout=0):
        """
        Writes data to the target over serial.

        Args:
            data (str): Data to write over serial.
            timeout (float or None): Wait <timeout> seconds for write buffer to clear.
                If None, block for a long time. If 0, return immediately. Defaults to 0.

        Raises:
            Warning: Target not connected
        """
        data = self.type_convert_data(data)

        self.ser.write(data, timeout)

    # Serial buffer status
    def in_waiting(self):
        """
        Returns the number of characters available from the serial buffer.

        Returns:
            The number of characters available via a target.read() call.
        """
        return self.ser.inWaiting()

    def flush(self):
        """
        Removes all data from the serial buffer.
        """
        self.ser.flush()

    def in_waiting_tx(self):
        """
        Returns the number of characters waiting to be sent by the ChipWhisperer.

        Requires firmware version >= 0.2 for the CWLite/Nano and firmware version and
        firmware version >= 1.2 for the CWPro.

        Returns:
            The number of characters waiting to be sent to the target
        """
        return self.ser.inWaitingTX()

    # Class print representations
    def __repr__(self):
        ret = "SimpleSerial Settings ="
        for line in dict_to_str(self._dict_repr()).split("\n"):
            ret += "\n\t" + line
        return ret

    def __str__(self):
        return self.__repr__()

    def _dict_repr(self):
        rtn = OrderedDict()
        rtn['output_len'] = self.output_len
        rtn['baud']     = self.baud
        rtn['parity'] = self.parity
        rtn['stop_bits'] = self.stop_bits
        return rtn

    # Serial device configuration
    @property
    def parity(self):
        if hasattr(self.ser, 'parity') and callable(self.ser.parity):
            return self.ser.parity()
        else:
            raise AttributeError("Can't access parity")

    @parity.setter
    def parity(self, parity):
        if hasattr(self.ser, 'parity') and callable(self.ser.parity):
            return self.ser.setParity(parity)
        else:
            raise AttributeError("Can't access parity")

    @property
    def stop_bits(self):
        if hasattr(self.ser, 'stopBits') and callable(self.ser.stopBits):
            return self.ser.stopBits()
        else:
            raise AttributeError("Can't access parity")

    @stop_bits.setter
    def stop_bits(self, stop_bits):
        if hasattr(self.ser, 'stopBits') and callable(self.ser.stopBits):
            return self.ser.setStopBits(stop_bits)
        else:
            raise AttributeError("Can't access parity")

    @property
    def baud(self):
        """
        The current baud rate of the serial connection.

        :Getter: Return the current baud rate.

        :Setter: Set a new baud rate. Valid baud rates are any integer in the
            range [500, 2000000].

        Raises:
            AttributeError: Can't access baud rate.
        """
        if hasattr(self.ser, 'baud') and callable(self.ser.baud):
            return self.ser.baud()
        else:
            raise AttributeError("Can't access baud rate")

    @baud.setter
    def baud(self, new_baud):
        if hasattr(self.ser, 'baud') and callable(self.ser.baud):
            self.ser.setBaud(new_baud)
        else:
            raise AttributeError("Can't access baud rate")


# class SimpleSerial2_CDC(SimpleSerial2): (TODO: usage with CDC Port -> see chipwhisperer SimpleSerial2.py)