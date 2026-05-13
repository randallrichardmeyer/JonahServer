import html
import urllib.parse


def render_salt_solver_page(player, render_page, session_token):
    escaped_token = urllib.parse.quote(session_token)

    body = f"""
    <div style="text-align: center;">
        <img
            src="/images/SaltSolver.png"
            alt="Salt Solver"
            style="display: block; max-width: 100%; width: 520px; margin: 0 auto 2rem auto;"
        >

        <a href="/salt-solver/new-game?token={escaped_token}" style="display: block; margin: 0 auto 1.5rem auto;">
            <img
                src="/images/NewGame.png"
                alt="New Game"
                style="display: block; max-width: 100%; width: 360px; margin: 0 auto;"
            >
        </a>

        <a class="oauth-button" href="/salt-solver/tutorial?token={escaped_token}">
            Tutorial
        </a>
    </div>

    <p>
        Welcome, {html.escape(player["name"])}. Choose an option to begin.
    </p>

    <a href="/">Back to login</a>
    """

    return render_page("Salt Solver", body)


def render_salt_solver_new_game_page(player, render_page, session_token):
    escaped_token = urllib.parse.quote(session_token)

    body = f"""
    <div style="text-align: center;">
        <img
            src="/images/SaltSolver.png"
            alt="Salt Solver"
            style="display: block; max-width: 100%; width: 520px; margin: 0 auto 2rem auto;"
        >

        <h2>New Game</h2>
        <p>
            Welcome, {html.escape(player["name"])}. Put your Salt Solver game here.
        </p>

        <div id="game">
            <p>Game area coming soon.</p>
        </div>

        <a class="oauth-button" href="/salt-solver?token={escaped_token}">
            Quit
        </a>
    </div>
    """

    return render_page("Salt Solver - New Game", body)


def render_salt_solver_tutorial_page(player, render_page, session_token):
    escaped_token = urllib.parse.quote(session_token)

    body = f"""
    <div style="text-align: center;">
        <img
            src="/images/SaltSolver.png"
            alt="Salt Solver"
            style="display: block; max-width: 100%; width: 520px; margin: 0 auto 2rem auto;"
        >

        <h2>Tutorial</h2>
        <p>
            Put your Salt Solver tutorial instructions here.
        </p>

        <a class="oauth-button" href="/salt-solver?token={escaped_token}">
            Back
        </a>
    </div>
    """

    return render_page("Salt Solver - Tutorial", body)