import socket
import threading
import time

import pytest
import uvicorn

from demo.server import create_app


@pytest.fixture
def live_server():
    """TCP real: Authlib y urllib3 no se sustituyen por dobles de HTTP."""
    app = create_app(token_lifetime=2)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started:
                if not thread.is_alive() or time.monotonic() > deadline:
                    pytest.fail("El servidor de prueba no arrancó")
                time.sleep(0.01)
            yield f"http://127.0.0.1:{port}", app
        finally:
            server.should_exit = True
            thread.join(timeout=5)
