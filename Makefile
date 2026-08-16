# Makefile for HomeSync agent project

.PHONY: install playground run test

install:
	uv sync

playground:
	uv run adk web app --host 127.0.0.1 --port 18081 --reload_agents

run:
	uv run uvicorn app.agent_runtime_app:app --host 0.0.0.0 --port $PORT

test:
	uv run pytest
