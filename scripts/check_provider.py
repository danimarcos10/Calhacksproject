"""Check the configured Claude model without printing the API key.

Run from the repository root:
  services\\api\\.venv\\Scripts\\python scripts\\check_provider.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

import anthropic

from app.config import Settings


def main() -> int:
    settings = Settings()
    if not settings.anthropic_api_key.strip():
        print("ANTHROPIC_API_KEY is not set")
        return 2
    print(f"configured_model={settings.anthropic_model}")
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=20, max_retries=0)
    try:
        page = client.models.list()
        ids = [item.id for item in page.data]
        print("account_models=" + ",".join(ids))
        print("configured_model_listed=" + str(settings.anthropic_model in ids))
    except anthropic.AuthenticationError:
        print("models.list=rejected")
        return 1
    except Exception:
        print("models.list=unavailable")
    try:
        model = client.models.retrieve(settings.anthropic_model)
    except anthropic.NotFoundError:
        print("configured_model_reachable=no")
        return 1
    except anthropic.AuthenticationError:
        print("configured_model_reachable=rejected")
        return 1
    except Exception:
        print("configured_model_reachable=error")
        return 1
    print(f"configured_model_reachable=yes id={model.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
