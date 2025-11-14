import socket
import time

def find_free_port(start=5000, end=5500, delay=0.2):
    """
    Find an available port to run the server with interval delay.
    """
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('127.0.0.1', port))
                print(f"++ Found open port on host '127.0.0.1': {port}")
                return port
            except OSError:
                time.sleep(delay)
                continue
    raise RuntimeError(f"No free port found in range {start}-{end}")