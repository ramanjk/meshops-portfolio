"""Allow `python -m mcp_servers.mlflow_mcp`."""
from .server import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
