# Jonah

A local Python web app for player login and the Salt Solver game.

## Requirements

- Python 3.9.6
- virtualenv
- ngrok

## Run the app locally

Start the server: bash python jonah.py

The app will run on: text [http://localhost:8000](http://localhost:8000)


Use `http://`, not `https://`.

## Use ngrok

ngrok lets you share your local server with a public URL.

First, make sure the Python server is already running on port `8000`.

Then, in another terminal, run: bash ngrok http 8000

ngrok will display a forwarding URL that looks something like: text [https://example-name.ngrok-free.app](https://example-name.ngrok-free.app)


Open that forwarding URL in a browser or share it with someone else.

## Notes

- Keep the Python server running while using ngrok.
- Keep the ngrok terminal open while using the public URL.
- If ngrok shows an error, restart the Python server first, then restart ngrok.
- If the browser complains about HTTPS locally, use `http://localhost:8000` for local testing.

