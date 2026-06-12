"""Mock HTTP server for integration testing.

Provides a simple, zero-dependency local web server serving a form login page
and a secure area to validate Playwright automation.
"""

import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

LOGIN_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Login Test Target</title>
</head>
<body>
    <h1>Login Page</h1>
    <form action="/login" method="POST">
        <div>
            <label for="username">Username</label>
            <input type="text" id="username" name="username" data-qa-id="username-input" placeholder="Enter username">
        </div>
        <div>
            <label for="password">Password</label>
            <input type="password" id="password" name="password" data-qa-id="password-input" placeholder="Enter password">
        </div>
        <button type="submit" id="submit-btn" data-qa-id="login-btn">Log In</button>
    </form>
</body>
</html>
"""

SECURE_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Secure Area</title>
</head>
<body>
    <h1>Secure Area</h1>
    <p id="success-msg">Welcome to the secure area! You are logged in.</p>
</body>
</html>
"""

FAILURE_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Login Failed</title>
</head>
<body>
    <h1>Login Failed</h1>
    <p id="error-msg">Invalid credentials. Try again.</p>
    <a href="/">Back to login</a>
</body>
</html>
"""


class MockServerRequestHandler(BaseHTTPRequestHandler):
    """Handles requests for the login integration mock server."""

    def log_message(self, format: str, *args: Any) -> None:
        """Supresses request console print logging to keep terminal test output clean."""
        pass

    def do_GET(self) -> None:
        """Serves GET pages."""
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path in ("/", "/login"):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(LOGIN_PAGE_HTML.encode("utf-8"))
        elif parsed_url.path == "/secure":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(SECURE_PAGE_HTML.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        """Handles credentials submit POST request."""
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == "/login":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length).decode("utf-8")
            params = urllib.parse.parse_qs(post_data)

            username = params.get("username", [""])[0]
            password = params.get("password", [""])[0]

            if username == "tomsmith" and password == "SuperSecretPassword!":
                # Success redirect or content
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(SECURE_PAGE_HTML.encode("utf-8"))
            else:
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(FAILURE_PAGE_HTML.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


class MockServer:
    """Zero-dependency Threading HTTPServer wrapping."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        """Sets up the mock server.

        Args:
            host: Binding address.
            port: Port to run on. If 0, binds to a random available port.
        """
        self.server = ThreadingHTTPServer((host, port), MockServerRequestHandler)
        host_val = self.server.server_address[0]
        self.host = (
            host_val.decode("utf-8") if isinstance(host_val, bytes) else str(host_val)
        )
        self.port = self.server.server_address[1]
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        """Returns the full address URL of the server."""
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        """Starts the server in a background thread."""
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Terminates the server and cleans up resources."""
        self.server.shutdown()
        self.server.server_close()
        if self._thread:
            self._thread.join()
