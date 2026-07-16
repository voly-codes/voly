"""Fixture module for FinOps benchmark tasks (intentional small defects)."""


def greet(name: str):
    return f"Helo, {name}!"


def main() -> None:
    print(greet("world"))


if __name__ == "__main__":
    main()
