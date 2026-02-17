# JediSOS

AI Agent System with Hindsight Memory + LangGraph + LiteLLM

## Quick Start

```bash
cp .env.example .env
# Edit .env with your API keys
docker compose -f docker-compose.dev.yml up -d
pip install -e ".[dev]"
make check
```

## License

MIT
