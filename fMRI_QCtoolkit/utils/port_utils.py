import socket
import time

def find_free_port(start=5000, end=5500, delay=0.2, host='127.0.0.1'):
    """
    Find an available port to run the server with interval delay.
    """
    for port in range(start, end):
        try:
            family, _, _, _, address = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0]
        except socket.gaierror as e:
            raise RuntimeError(f"Cannot resolve host {host}: {e}")
        # No SO_REUSEADDR: on Windows it lets the bind succeed on a port another server is listening on
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(address)
                print(f"++ Found open port on host '{host}': {port}")
                return port
            except OSError:
                time.sleep(delay)
                continue
    raise RuntimeError(f"No free port found in range {start}-{end}")
