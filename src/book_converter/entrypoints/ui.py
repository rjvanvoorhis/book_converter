import pathlib
import shutil
import subprocess
import sys

# The Angular app is a sibling of src/, not part of the Python package, so it
# has to be located relative to this file rather than imported.
_UI_DIR = pathlib.Path(__file__).resolve().parents[3] / "ui"


def main() -> None:
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm is required to run the UI but was not found on PATH")

    if not (_UI_DIR / "node_modules").exists():
        subprocess.run([npm, "install"], cwd=_UI_DIR, check=True)

    args = [npm, "start"]
    if len(sys.argv) > 1:
        args += ["--", *sys.argv[1:]]
    result = subprocess.run(args, cwd=_UI_DIR, check=False)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
