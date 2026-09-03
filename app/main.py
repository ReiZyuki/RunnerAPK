import ast
import importlib.util
import os
import re
import runpy
import sys
import threading
import time
import traceback

from android.permissions import request_permissions, Permission
from android.storage import primary_external_storage_path


# ============================================================
# CONFIG
# ============================================================

RUNNER_FOLDER = "Runner"
RUN_FILE_NAME = "Run.py"

URL_PATTERN = re.compile(
    r"FLASK_URL\s*=\s*(https?://[^\s]+)"
)


# ============================================================
# GLOBAL STATE
# ============================================================

runner_url = None
runner_error = None
runner_started = False
runner_finished = False


# ============================================================
# FIND RUNNER DIRECTORY
# ============================================================

def get_runner_directory():
    external = primary_external_storage_path()

    return os.path.join(
        external,
        "Download",
        RUNNER_FOLDER
    )


# ============================================================
# FIND RUN.PY
# ============================================================

def get_run_file():
    folder = get_runner_directory()

    return os.path.join(
        folder,
        RUN_FILE_NAME
    )


# ============================================================
# IMPORT → PACKAGE MAP
# ============================================================

PACKAGE_MAP = {
    "flask": "flask",
    "telebot": "telebot",
    "requests": "requests",
    "bs4": "bs4",
    "PIL": "PIL",
    "numpy": "numpy",
    "yaml": "yaml",
}


# ============================================================
# READ IMPORTS
# ============================================================

def detect_imports(path):

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        source = file.read()

    tree = ast.parse(source)

    modules = set()

    for node in ast.walk(tree):

        if isinstance(
            node,
            ast.Import
        ):

            for item in node.names:
                modules.add(
                    item.name.split(".")[0]
                )

        elif isinstance(
            node,
            ast.ImportFrom
        ):

            if node.module:
                modules.add(
                    node.module.split(".")[0]
                )

    return sorted(modules)


# ============================================================
# CHECK INSTALLED PACKAGES
# ============================================================

def check_dependencies(imports):

    missing = []

    for module in imports:

        if module in {
            "os",
            "sys",
            "re",
            "json",
            "time",
            "threading",
            "socket",
            "pathlib",
            "math",
            "random",
            "datetime",
            "typing",
            "subprocess",
            "traceback",
            "ast",
            "io",
            "logging",
        }:

            continue

        try:

            if importlib.util.find_spec(
                module
            ) is None:

                missing.append(
                    PACKAGE_MAP.get(
                        module,
                        module
                    )
                )

        except Exception:

            missing.append(
                PACKAGE_MAP.get(
                    module,
                    module
                )
            )

    return sorted(
        set(missing)
    )


# ============================================================
# OUTPUT CAPTURE
# ============================================================

class RunnerOutput:

    def __init__(self, original):
        self.original = original

    def write(self, text):

        global runner_url

        self.original.write(text)
        self.original.flush()

        match = URL_PATTERN.search(
            text
        )

        if match:

            runner_url = (
                match.group(1)
                .rstrip(".,;")
            )

        return len(text)

    def flush(self):
        self.original.flush()

    def fileno(self):
        return self.original.fileno()


# ============================================================
# EXECUTE RUN.PY
# ============================================================

def execute_run_file():

    global runner_error
    global runner_started
    global runner_finished

    run_file = get_run_file()

    if not os.path.isdir(
        get_runner_directory()
    ):

        runner_error = (
            "Runner folder not found:\n\n"
            + get_runner_directory()
        )

        return

    if not os.path.isfile(
        run_file
    ):

        runner_error = (
            "Run.py not found:\n\n"
            + run_file
        )

        return

    try:

        runner_started = True

        os.chdir(
            get_runner_directory()
        )

        imports = detect_imports(
            run_file
        )

        missing = check_dependencies(
            imports
        )

        if missing:

            runner_error = (
                "Missing Python packages:\n\n"
                + "\n".join(missing)
                + "\n\n"
                "These packages must be included "
                "in the Runner APK build."
            )

            return

        original_stdout = sys.stdout
        original_stderr = sys.stderr

        sys.stdout = RunnerOutput(
            original_stdout
        )

        sys.stderr = RunnerOutput(
            original_stderr
        )

        try:

            runpy.run_path(
                run_file,
                run_name="__main__"
            )

        finally:

            sys.stdout = original_stdout
            sys.stderr = original_stderr

    except SystemExit:

        pass

    except Exception:

        runner_error = traceback.format_exc()

    finally:

        runner_finished = True


# ============================================================
# START RUNNER
# ============================================================

def start_runner():

    thread = threading.Thread(
        target=execute_run_file,
        daemon=True
    )

    thread.start()

    return thread


# ============================================================
# ANDROID STORAGE PERMISSION
# ============================================================

def request_storage():

    try:

        request_permissions([
            Permission.READ_EXTERNAL_STORAGE,
            Permission.WRITE_EXTERNAL_STORAGE,
        ])

    except Exception:
        pass


# ============================================================
# MAIN
# ============================================================

def main():

    request_storage()

    start_runner()


if __name__ == "__main__":

    main()
