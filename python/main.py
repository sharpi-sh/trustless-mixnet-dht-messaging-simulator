"""Bind once and hand the same loopback socket to Uvicorn."""

import argparse
import errno
import socket

import uvicorn

from app.server import app


def bind_local(first: int, last: int) -> socket.socket:
    for port in range(first, last + 1):
        sock = socket.socket()
        try:
            sock.bind(("127.0.0.1", port))
            sock.setblocking(False)
        except OSError as exc:
            sock.close()
            if exc.errno == errno.EADDRINUSE:
                continue
            raise
        return sock
    raise RuntimeError(f"No available loopback port in {first}–{last}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-port", type=int, default=8000)
    parser.add_argument("--last-port", type=int, default=8099)
    args = parser.parse_args()
    with bind_local(args.first_port, args.last_port) as sock:
        port = sock.getsockname()[1]
        app.state.port = port
        print(
            f"HTTP API: http://127.0.0.1:{port}\nWebSocket: ws://127.0.0.1:{port}/ws\n"
            "Ready for frontend connection.",
            flush=True,
        )
        uvicorn.Server(uvicorn.Config(app, loop="asyncio")).run(sockets=[sock])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
