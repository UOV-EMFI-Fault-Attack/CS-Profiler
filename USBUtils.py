import os
import subprocess

def find_usb_port_by_dev_path(dev_path : str) -> tuple[str, str]:
    """
    Find the USB hub_path and hub_port_num of a USB device by it's device path in the devfs.
    The hub_path and hub_port_num can be used with uhubctl for power switching (if the USB hub supports it).

    Args:
        dev_path (str): Devfs path of the USB device

    Raises:
        Exception: When no valid USB hub_path and hub_port_num can be found.

    Returns:
        tuple[str, str]: (hub_path, hub_port_num)
    """

    # Get sysfs path using udevadm
    try:
        usb_rel_path = subprocess.check_output(
            ["udevadm", "info", "-q", "path", "-n", dev_path],
            text=True
        ).strip()
    except subprocess.CalledProcessError:
        raise RuntimeError(
            f"Could not get sysfs path for {dev_path}\n"
        )

    # Walk up until we find a directory with idVendor
    device_dir = "/sys" + usb_rel_path
    while not os.path.exists(os.path.join(device_dir, "idVendor")):
        new_dir = os.path.dirname(device_dir)
        if new_dir == device_dir:
            raise ValueError(f"Could not find idVendor for {dev_path}")
        device_dir = new_dir

    # Extract device bus and port path
    device_name = os.path.basename(device_dir)  # e.g. 1-1.2
    parts = device_name.split(".")

    if len(parts) > 1:
        # Normal case (format: <hub>-<sub>.<port>)
        #   number behind last "." is port, everything before is hub path
        hub_port_num = parts[-1]
        hub_path = ".".join(parts[:-1])

    elif "-" in device_name:
        # Shortest case (format: <hub>-<port>)
        hub_path, hub_port_num = device_name.rsplit("-", 1)

    else:
        # Unsupported format
        raise ValueError(
            f"Unexpected device name format `{device_name}` "
            "(expected <hub>-<port> or <hub>-<sub>.<port>)"
        )

    return hub_path, hub_port_num

def find_usb_port_by_busdev(bus_num : int, dev_num : int) -> tuple[str, str]:
    """
    Find the USB hub_path and hub_port_num of a USB device by it's Bus and Device Number (can be found which `lsusb`).
    The hub_path and hub_port_num can be used with uhubctl for power switching (if the USB hub supports it).

    Args:
        bus_num (int): Bus number of the USB device (check `lsusb`)
        dev_num (int): Device number of the USB device (check `lsusb`)

    Raises:
        Exception: When no valid USB hub_path and hub_port_num can be found.

    Returns:
        tuple[str, str]: (hub_path, hub_port_num)
    """

    # Zero-pad bus and device to 3 digits
    bus_str = f"{int(bus_num):03d}"
    dev_str = f"{int(dev_num):03d}"
    dev_path = f"/dev/bus/usb/{bus_str}/{dev_str}"

    if not os.path.exists(dev_path):
        raise ValueError(f"USB device {bus_num}:{dev_num} not found")

    return find_usb_port_by_dev_path(dev_path)

def find_usb_port_by_tty(tty : str) -> tuple[str, str]:
    """
    Find the USB hub_path and hub_port_num of a USB device by it's tty path
    The hub_path and hub_port_num can be used with uhubctl for power switching (if the USB hub supports it).

    Args:
        tty (str): Path of the tty device

    Raises:
        Exception: When no valid USB hub_path and hub_port_num can be found.

    Returns:
        tuple[str, str]: (hub_path, hub_port_num)
    """

    if not tty.startswith("/dev/tty"):
        tty = f"/dev/{tty}"

    return find_usb_port_by_dev_path(tty)



def find_tty_by_id(serial_id : str) -> str:
    """
    Find the tty device path of a device by it's serial_id (using /dev/serial/by-id)
    Substring matching is used (check if one of the files in /dev/serial/by-id CONTAINS serial_id parameter)

    Args:
        serial_id (str): _description_

    Raises:
        ValueError: Multiple devices match the passed `serial_id` substring
        FileNotFoundError: Could not find a connected device that matches the passed `seria_id` substring.

    Returns:
        str: Path to tty device (/dev/tty...)
    """

    by_id_path = "/dev/serial/by-id"
    if not os.path.exists(by_id_path):
        raise FileNotFoundError("Serial ID directory '/dev/serial/by-id/' does not exist.")

    # Manual pattern matching
    matches = []
    for name in os.listdir(by_id_path):
        if serial_id in name:  # substring match
            full_path = os.path.join(by_id_path, name)
            matches.append(os.path.realpath(full_path))

    if not matches:
        raise FileNotFoundError(
            f"No device found with serial ID containing '{serial_id}'."
        )
    elif len(matches) > 1:
        raise ValueError(
            f"Multiple devices match serial ID '{serial_id}' ({', '.join(matches)}).  Please pass the tty device or exact serial id. "
        )

    return matches[0]