import ast
import builtins
import os
import re
import runpy
import socket
import sys
import threading
import traceback

from flask import Flask, Response


# ============================================================
# CONFIG
# ============================================================

RUNNER_DIR = "/storage/emulated/0/Download/Runner"
RUN_FILE = os.path.join(RUNNER_DIR, "Run.py")

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 5000

URL_PATTERN = re.compile(
    r"FLASK_URL\s*=\s*(https?://[^\s]+)"
)


# ============================================================
# GLOBAL STATE
# ============================================================

runner_url = None
runner_error = None
runner_status = "Starting Runner..."


# ============================================================
# FLASK BRIDGE
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():

    global runner_url
    global runner_error
    global runner_status

    # --------------------------------------------------------
    # Run.py successfully provided URL
    # --------------------------------------------------------

    if runner_url:

        return Response(
            f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
http-equiv="refresh"
content="0; url={runner_url}">

<title>Runner</title>

</head>

<body>

Opening Runner...

<script>
window.location.replace("{runner_url}");
</script>

</body>

</html>
""",
            mimetype="text/html",
        )

    # --------------------------------------------------------
    # Error
    # --------------------------------------------------------

    if runner_error:

        safe_error = (
            runner_error
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

        return Response(
            f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width, initial-scale=1">

<title>Runner Error</title>

<style>

body {{
    margin: 0;
    padding: 20px;
    background: #111;
    color: white;
    font-family: sans-serif;
}}

pre {{
    white-space: pre-wrap;
    word-break: break-word;
}}

</style>

</head>

<body>

<h2>Runner Error</h2>

<pre>{safe_error}</pre>

</body>

</html>
""",
            status=500,
            mimetype="text/html",
        )

    # --------------------------------------------------------
    # Still starting
    # --------------------------------------------------------

    return Response(
        f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width, initial-scale=1">

<meta
http-equiv="refresh"
content="1">

<title>Runner</title>

<style>

body {{
    margin: 0;
    background: #111;
    color: white;
    font-family: sans-serif;

    display: flex;

    align-items: center;

    justify-content: center;

    height: 100vh;
}}

.box {{
    text-align: center;
}}

.loader {{
    width: 35px;
    height: 35px;

    border: 4px solid #333;
    border-top: 4px solid #9205f2;

    border-radius: 50%;

    margin: auto auto 20px auto;

    animation: spin 1s linear infinite;
}}

@keyframes spin {{

    from {{
        transform: rotate(0deg);
    }}

    to {{
        transform: rotate(360deg);
    }}
}}

</style>

</head>

<body>

<div class="box">

<div class="loader"></div>

<h2>{runner_status}</h2>

</div>

</body>

</html>
""",
        mimetype="text/html",
    )


# ============================================================
# IMPORT DETECTION
# ============================================================

def detect_imports(file_path):

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:

        source = file.read()

    tree = ast.parse(source)

    imports = set()

    for node in ast.walk(tree):

        if isinstance(node, ast.Import):

            for item in node.names:

                imports.add(
                    item.name.split(".")[0]
                )

        elif isinstance(node, ast.ImportFrom):

            if node.module:

                imports.add(
                    node.module.split(".")[0]
                )

    return sorted(imports)


# ============================================================
# PACKAGE CHECK
# ============================================================

def check_imports(imports):

    missing = []

    for module in imports:

        # Built-in Python modules
        if module in sys.builtin_module_names:
            continue

        # Try to import package
        try:

            __import__(module)

        except ImportError:

            missing.append(module)

        except Exception:

            # Package exists but import caused
            # another runtime error.
            pass

    return missing


# ============================================================
# OUTPUT CAPTURE
# ============================================================

class OutputCapture:

    def __init__(
        self,
        original
    ):

        self.original = original

        self.buffer = ""


    def write(
        self,
        text
    ):

        global runner_url

        # Show output normally
        self.original.write(text)

        self.original.flush()

        # Add to buffer because print output
        # can arrive in pieces.
        self.buffer += text

        # Limit buffer size
        if len(self.buffer) > 10000:

            self.buffer = self.buffer[-5000:]

        # Search URL
        match = URL_PATTERN.search(
            self.buffer
        )

        if match:

            runner_url = (
                match.group(1)
                .strip()
                .rstrip(".,;")
            )

        return len(text)


    def flush(self):

        self.original.flush()


# ============================================================
# RUN EXTERNAL PYTHON FILE
# ============================================================

def run_external_file():

    global runner_error
    global runner_status

    try:

        # ----------------------------------------------------
        # Folder check
        # ----------------------------------------------------

        runner_status = (
            "Scanning Download/Runner..."
        )

        if not os.path.isdir(
            RUNNER_DIR
        ):

            runner_error = (
                "Runner folder not found:\n\n"
                + RUNNER_DIR
            )

            return


        # ----------------------------------------------------
        # Run.py check
        # ----------------------------------------------------

        runner_status = (
            "Searching Run.py..."
        )

        if not os.path.isfile(
            RUN_FILE
        ):

            runner_error = (
                "Run.py not found:\n\n"
                + RUN_FILE
            )

            return


        # ----------------------------------------------------
        # Import scan
        # ----------------------------------------------------

        runner_status = (
            "Checking Python imports..."
        )

        imports = detect_imports(
            RUN_FILE
        )

        missing = check_imports(
            imports
        )

        # ----------------------------------------------------
        # Missing dependency
        # ----------------------------------------------------

        if missing:

            runner_error = (
                "Unsupported or missing packages:\n\n"
                + "\n".join(missing)
                + "\n\n"
                + "These packages must be included "
                + "when building Runner.apk."
            )

            return


        # ----------------------------------------------------
        # Execute
        # ----------------------------------------------------

        runner_status = (
            "Starting Run.py..."
        )

        # Run.py relative files work from Runner folder
        os.chdir(
            RUNNER_DIR
        )

        # Ensure imports from Runner folder work
        if RUNNER_DIR not in sys.path:

            sys.path.insert(
                0,
                RUNNER_DIR
            )

        original_stdout = sys.stdout
        original_stderr = sys.stderr

        capture_stdout = OutputCapture(
            original_stdout
        )

        capture_stderr = OutputCapture(
            original_stderr
        )

        sys.stdout = capture_stdout
        sys.stderr = capture_stderr

        try:

            runpy.run_path(
                RUN_FILE,
                run_name="__main__"
            )

        finally:

            sys.stdout = original_stdout
            sys.stderr = original_stderr


    except SystemExit:

        pass


    except Exception:

        runner_error = traceback.format_exc()


# ============================================================
# START EXTERNAL RUNNER
# ============================================================

def start_runner():

    thread = threading.Thread(
        target=run_external_file,
        daemon=True
    )

    thread.start()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # Start external Run.py in background
    start_runner()

    # This is the URL initially opened
    # by python-for-android WebView.
    app.run(
        host=BRIDGE_HOST,
        port=BRIDGE_PORT,
        debug=False,
        use_reloader=False
    )
