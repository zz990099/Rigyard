"""Generate a complete Dockerfile around a validated layer fragment."""


def compose_dockerfile(base_image: str, fragment: str) -> str:
    return f"FROM {base_image}\n\n{fragment.rstrip()}\n"

