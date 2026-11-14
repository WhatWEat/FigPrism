"""Convert the supplied text snippets without executing shell or exposing secrets."""

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import yaml


def convert(source: Path, output: Path):
    dav = {}
    for line in (source / "webdav.txt").read_text().splitlines():
        key, sep, value = line.partition(":")
        if sep:
            dav[key.strip()] = value.strip().strip("\"'")
    api = (source / "api.txt").read_text()
    url = re.search(r"https?://[^\s'\"\\]+", api)
    token = re.search(r"Authorization:\s*Bearer\s+([^\s'\"\\]+)", api, re.I)
    model = re.search(r'"model"\s*:\s*"([^\"]+)"', api)
    if not (
        url
        and token
        and model
        and dav.get("url")
        and dav.get("username")
        and dav.get("password")
    ):
        raise ValueError(
            "Missing required API or WebDAV fields; inspect source files locally"
        )
    config = {
        "secret_key": secrets.token_urlsafe(48),
        "webdav": {
            "url": dav["url"].rstrip("/"),
            "username": dav["username"],
            "password": dav["password"],
            "root": (
                "/figprism"
                if ">" in dav.get("dir", "")
                else dav.get("dir", "/figprism")
            ),
        },
        "vision": {
            "base_url": re.sub(r"/chat/completions/?$", "", url.group()),
            "api_key": token.group(1),
            "model": model.group(1),
            "driver": "openai_mini",
        },
    }
    # Exclusive creation avoids silently rotating an existing application's signing key.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    print(f"Converted configuration to {output}; secrets hidden, mode 0600")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("config"))
    parser.add_argument("--output", type=Path, default=Path("config/local.yaml"))
    args = parser.parse_args()
    convert(args.source, args.output)
