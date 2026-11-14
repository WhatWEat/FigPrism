"""Create a dedicated local test account without logging its password."""

import json
import os
from pathlib import Path
import secrets
from figprism.auth import create_user
from figprism.db import init_db

if __name__ == "__main__":
    init_db()
    path = Path("data/qa/e2e-account.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        print("QA account file already exists; preserved.")
    else:
        username = "qa_" + secrets.token_hex(4)
        password = secrets.token_urlsafe(20)
        uid = create_user(username, password)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as file:
            json.dump({"username": username, "password": password, "id": uid}, file)
        print(f"QA account created; credentials stored privately in {path}.")
