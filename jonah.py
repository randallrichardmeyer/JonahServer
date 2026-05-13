from http.server import HTTPServer, BaseHTTPRequestHandler
import html
import json
import os
import secrets
import socket
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import parse_qs, urlparse

from database import initialize_database, login_or_create_player, login_or_create_oauth_player
from saltsolver import (
    render_salt_solver_new_game_page,
    render_salt_solver_page,
    render_salt_solver_tutorial_page,
)

OAUTH_STATES = set()
PLAYER_SESSIONS = {}

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"

client_id = os.environ.get("GOOGLE_CLIENT_ID")


class FriendlyHTTPServer(HTTPServer):
    def handle_error(self, request, client_address):
        print(f"Connection error from {client_address[0]}:{client_address[1]}")


class MobileServerHandler(BaseHTTPRequestHandler):
    def handle_one_request(self):
        try:
            first_bytes = self.rfile.peek(3)[:3]

            if first_bytes and first_bytes[0] == 0x16 and first_bytes[1] == 0x03:
                print(
                    f"HTTPS request received from {self.client_address[0]}. "
                    "This server uses HTTP, not HTTPS. "
                    f"Open http://{get_local_ip()}:8000 instead."
                )
                self.close_connection = True
                return

            super().handle_one_request()
        except ConnectionResetError:
            self.close_connection = True

    def send_html_response(self, html_content):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))

    def send_file_response(self, file_path, content_type):
        try:
            with open(file_path, "rb") as file:
                file_content = file.read()
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(file_content)

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self):
        parsed_url = urlparse(self.path)

        if parsed_url.path.startswith("/images/") and parsed_url.path.endswith(".png"):
            image_name = os.path.basename(parsed_url.path)
            self.send_file_response(f"images/{image_name}", "image/png")
            return

        if parsed_url.path == "/oauth/google/start":
            self.start_google_oauth()
            return

        if parsed_url.path == "/oauth/google/callback":
            self.handle_google_oauth_callback(parsed_url)
            return

        if parsed_url.path == "/salt-solver":
            self.show_salt_solver(parsed_url)
            return

        if parsed_url.path == "/salt-solver/new-game":
            self.show_salt_solver_new_game(parsed_url)
            return

        if parsed_url.path == "/salt-solver/tutorial":
            self.show_salt_solver_tutorial(parsed_url)
            return

        self.send_html_response(render_login_page())

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        form_data = parse_qs(raw_body)

        username = form_data.get("username", [""])[0].strip()
        password = form_data.get("password", [""])[0]

        if not username or not password:
            self.send_html_response(
                render_login_page("Username and password are required.")
            )
            return

        result = login_or_create_player(username, password)

        if not result["success"]:
            self.send_html_response(render_login_page(result["message"]))
            return

        session_token = create_player_session(result["player"])

        self.send_html_response(
            render_player_stats_page(
                player=result["player"],
                message=result["message"],
                created=result["created"],
                session_token=session_token,
            )
        )

    def show_salt_solver(self, parsed_url):
        query_parameters = parse_qs(parsed_url.query)
        session_token = query_parameters.get("token", [""])[0]
        player = PLAYER_SESSIONS.get(session_token)

        if player is None:
            self.send_html_response(
                render_login_page("Please log in before playing Salt Solver.")
            )
            return

        self.send_html_response(
            render_salt_solver_page(player, render_page, session_token)
        )

    def show_salt_solver_new_game(self, parsed_url):
        query_parameters = parse_qs(parsed_url.query)
        session_token = query_parameters.get("token", [""])[0]
        player = PLAYER_SESSIONS.get(session_token)

        if player is None:
            self.send_html_response(
                render_login_page("Please log in before playing Salt Solver.")
            )
            return

        self.send_html_response(
            render_salt_solver_new_game_page(player, render_page, session_token)
        )

    def show_salt_solver_tutorial(self, parsed_url):
        query_parameters = parse_qs(parsed_url.query)
        session_token = query_parameters.get("token", [""])[0]
        player = PLAYER_SESSIONS.get(session_token)

        if player is None:
            self.send_html_response(
                render_login_page("Please log in before playing Salt Solver.")
            )
            return

        self.send_html_response(
            render_salt_solver_tutorial_page(player, render_page, session_token)
        )

    def start_google_oauth(self):
        client_id = os.environ.get("GOOGLE_CLIENT_ID")
        redirect_uri = os.environ.get(
            "OAUTH_REDIRECT_URI",
            "http://localhost:8000/oauth/google/callback",
        )

        if not client_id:
            self.send_html_response(
                render_login_page("GOOGLE_CLIENT_ID environment variable is missing.")
            )
            return

        state = secrets.token_urlsafe(32)
        OAUTH_STATES.add(state)

        query_parameters = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "prompt": "select_account",
            }
        )

        self.redirect(f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{query_parameters}")

    def handle_google_oauth_callback(self, parsed_url):
        query_parameters = parse_qs(parsed_url.query)

        oauth_error = query_parameters.get("error", [""])[0]
        if oauth_error:
            self.send_html_response(render_login_page(f"OAuth failed: {oauth_error}"))
            return

        code = query_parameters.get("code", [""])[0]
        state = query_parameters.get("state", [""])[0]

        if not code or not state:
            self.send_html_response(
                render_login_page("OAuth response was missing required data.")
            )
            return

        if state not in OAUTH_STATES:
            self.send_html_response(
                render_login_page("Invalid OAuth state. Please try again.")
            )
            return

        OAUTH_STATES.remove(state)

        try:
            token_data = exchange_google_code_for_tokens(code)
            access_token = token_data.get("access_token")

            if not access_token:
                self.send_html_response(
                    render_login_page("OAuth provider did not return an access token.")
                )
                return

            userinfo = get_google_userinfo(access_token)

            provider_user_id = userinfo.get("sub")
            email = userinfo.get("email")
            name = userinfo.get("name") or email

            if not provider_user_id:
                self.send_html_response(
                    render_login_page("OAuth provider did not return a user ID.")
                )
                return

            result = login_or_create_oauth_player(
                provider="google",
                provider_user_id=provider_user_id,
                email=email,
                name=name,
            )

            if not result["success"]:
                self.send_html_response(render_login_page(result["message"]))
                return

            session_token = create_player_session(result["player"])

            self.send_html_response(
                render_player_stats_page(
                    player=result["player"],
                    message=result["message"],
                    created=result["created"],
                    session_token=session_token,
                )
            )
        except RuntimeError as error:
            self.send_html_response(render_login_page(str(error)))


def render_page(title, body):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{html.escape(title)}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                font-family: Arial, sans-serif;
                padding: 2rem;
                background: #f4f4f4;
            }}

            .card {{
                background: white;
                padding: 2rem;
                border-radius: 12px;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
                max-width: 650px;
                margin: 0 auto;
            }}

            label {{
                display: block;
                margin-top: 1rem;
                font-weight: bold;
            }}

            input {{
                width: 100%;
                padding: 0.75rem;
                margin-top: 0.25rem;
                box-sizing: border-box;
                border: 1px solid #ccc;
                border-radius: 8px;
                font-size: 1rem;
            }}

            button, .oauth-button {{
                display: block;
                margin-top: 1.25rem;
                padding: 0.75rem 1rem;
                width: 100%;
                box-sizing: border-box;
                border: none;
                border-radius: 8px;
                background: #2563eb;
                color: white;
                font-size: 1rem;
                cursor: pointer;
                text-align: center;
                text-decoration: none;
            }}

            button:hover, .oauth-button:hover {{
                background: #1d4ed8;
            }}

            .error {{
                padding: 1rem;
                border-radius: 8px;
                background: #fee2e2;
                color: #991b1b;
                margin-bottom: 1rem;
            }}

            .success {{
                padding: 1rem;
                border-radius: 8px;
                background: #dcfce7;
                color: #166534;
                margin-bottom: 1rem;
            }}

            pre {{
                overflow-x: auto;
                background: #222;
                color: #eee;
                padding: 1rem;
                border-radius: 8px;
            }}

            hr {{
                margin: 2rem 0;
                border: none;
                border-top: 1px solid #ddd;
            }}

            a {{
                display: inline-block;
                margin-top: 1rem;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            {body}
        </div>
    </body>
    </html>
    """


def render_login_page(error_message=None):
    error_html = ""

    if error_message:
        error_html = f'<div class="error">{html.escape(error_message)}</div>'

    body = f"""
    <h1>Player Login</h1>
    <p>
        Log in to view your stats. If your username does not exist yet,
        a new account will be created automatically with all stats set to zero.
    </p>

    {error_html}

    <a class="oauth-button" href="/oauth/google/start">
        Sign in with Google
    </a>

    <hr>

    <form method="POST" action="/">
        <label for="username">Username</label>
        <input id="username" name="username" type="text" autocomplete="username" required>

        <label for="password">Password</label>
        <input id="password" name="password" type="password" autocomplete="current-password" required>

        <button type="submit">Log In / Create Account</button>
    </form>
    """

    return render_page("Player Login", body)


def create_player_session(player):
    session_token = secrets.token_urlsafe(32)
    PLAYER_SESSIONS[session_token] = player
    return session_token


def render_player_stats_page(player, message, created, session_token):
    metadata_json = json.dumps(player["metadata"], indent=4)
    message_class = "success"
    salt_solver_url = f"/salt-solver?token={urllib.parse.quote(session_token)}"

    body = f"""
    <h1>{html.escape(player["name"])}'s Stats</h1>
    <div class="{message_class}">{html.escape(message)}</div>

    <a class="oauth-button" href="{salt_solver_url}">
        Play Salt Solver
    </a>

    <h2>Account</h2>
    <p><strong>Username:</strong> {html.escape(player["username"])}</p>
    <p><strong>Player UUID:</strong> {html.escape(player["uuid"])}</p>
    <p><strong>Class:</strong> {html.escape(player["currentclass"])}</p>
    <p><strong>Location:</strong> {player["locationx"]}, {player["locationy"]}</p>
    <p><strong>New account:</strong> {"Yes" if created else "No"}</p>

    <h2>Stats</h2>
    <pre>{html.escape(metadata_json)}</pre>

    <a href="/">Back to login</a>
    """

    return render_page("Player Stats", body)


def exchange_google_code_for_tokens(code):
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.environ.get(
        "OAUTH_REDIRECT_URI",
        "http://localhost:8000/oauth/google/callback",
    )

    if not client_id:
        raise RuntimeError("GOOGLE_CLIENT_ID environment variable is missing.")

    if not client_secret:
        raise RuntimeError("GOOGLE_CLIENT_SECRET environment variable is missing.")

    request_body = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        GOOGLE_TOKEN_ENDPOINT,
        data=request_body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8")
        raise RuntimeError(f"OAuth token exchange failed: {error_body}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not connect to OAuth provider: {error}") from error


def get_google_userinfo(access_token):
    request = urllib.request.Request(
        GOOGLE_USERINFO_ENDPOINT,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8")
        raise RuntimeError(f"OAuth user info request failed: {error_body}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not connect to OAuth provider: {error}") from error


def get_local_ip():
    socket_connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        socket_connection.connect(("8.8.8.8", 80))
        local_ip = socket_connection.getsockname()[0]
    except OSError:
        local_ip = "127.0.0.1"
    finally:
        socket_connection.close()

    return local_ip


def run_server():
    initialize_database()

    host = "0.0.0.0"
    port = 8000

    server = FriendlyHTTPServer((host, port), MobileServerHandler)
    local_ip = get_local_ip()

    print("Server is running.")
    print(f"Open this on your computer: http://localhost:{port}")
    print(f"Open this on your phone:    http://{local_ip}:{port}")
    print()
    print("Important: use http://, not https://")
    print("Press Ctrl+C to stop the server.")

    server.serve_forever()


if __name__ == "__main__":
    run_server()