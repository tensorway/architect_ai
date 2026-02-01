"""Flask microservice that exposes the Architect agent over HTTP."""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any, Dict, List

import requests
from flask import Flask, jsonify, request

from agent.architect_agent import ArchitectAgentInput, build_architect_agent
from agent.logging.checkpoints import (
    log_checkpoint,
    reset_checkpoint_callback,
    set_checkpoint_callback,
)
from config import load_settings


def _build_response_payload(result, checkpoints: List[str]) -> Dict[str, Any]:
    plan = {
        "walls": result.walls,
        "rooms": result.rooms,
        "assets": result.assets,
        "roomRequirements": result.roomRequirements,
    }
    return {
        "plan": plan,
        "view": result.view,
        "prompt": result.prompt,
        "notes": result.notes,
        "checkpoints": checkpoints,
    }


def create_app() -> Flask:
    """Create and configure the Flask application."""
    load_settings()
    app = Flask(__name__)

    agent = build_architect_agent()

    @app.after_request
    def _add_cors_headers(response):
        response.headers.setdefault("Access-Control-Allow-Origin", "*")
        response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type")
        response.headers.setdefault("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        return response

    @app.get("/health")
    def health() -> Any:
        return {"status": "ok"}, HTTPStatus.OK

    @app.route("/architect/generate", methods=["POST", "OPTIONS"])
    def generate_plan() -> Any:
        if request.method == "OPTIONS":
            return ("", HTTPStatus.NO_CONTENT)

        payload = request.get_json(silent=True) or {}
        prompt = (payload.get("prompt") or "").strip()
        if not prompt:
            return (
                jsonify({"error": "The 'prompt' field is required."}),
                HTTPStatus.BAD_REQUEST,
            )

        checkpoint_messages: list[str] = []
        callback_url = (payload.get("checkpoint_callback_url") or "").strip()

        def _emit_checkpoint(message: str) -> None:
            checkpoint_messages.append(message)
            if not callback_url:
                return
            try:
                requests.post(
                    callback_url,
                    json={"message": message},
                    timeout=1,
                )
            except requests.RequestException:
                logging.debug("Unable to forward checkpoint update.", exc_info=True)

        token = set_checkpoint_callback(_emit_checkpoint)
        try:
            log_checkpoint("Understanding the design brief…")
            result = agent.run(ArchitectAgentInput(prompt=prompt))
            log_checkpoint("Plan ready.")
        except Exception as exc:  # pragma: no cover - defensive logging
            logging.exception("Architect agent failed: %s", exc)
            return (
                jsonify({"error": "Unable to generate a plan at the moment."}),
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        finally:
            reset_checkpoint_callback(token)

        return (
            jsonify(_build_response_payload(result, checkpoint_messages)),
            HTTPStatus.OK,
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
