"""Run the single EXE from an isolated directory without Python on PATH."""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--expected-heroes", help="Comma-separated champion IDs for the supplied image")
    args = parser.parse_args()
    executable = ROOT / "dist" / "海克斯助手.exe"
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    isolated = Path(tempfile.mkdtemp(prefix="single-exe-", dir=artifacts))
    run_dir = isolated / "仅一个文件"
    run_dir.mkdir()
    copied = run_dir / executable.name
    shutil.copy2(executable, copied)
    environment = os.environ.copy()
    environment["PATH"] = str(Path(environment.get("SystemRoot", "C:/Windows")) / "System32")
    environment["LOCALAPPDATA"] = str(isolated / "user-data")
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV"):
        environment.pop(key, None)
    report_path = isolated / "self-test.json"
    command = [str(copied), "--self-test", str(report_path)]
    if args.image:
        command.extend(["--self-test-image", str(args.image.resolve())])
    result = subprocess.run(command, cwd=run_dir,
        env=environment, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["exit_code"] = result.returncode
    report["isolated_directory_files"] = [p.name for p in run_dir.iterdir()]
    report["exe_size_bytes"] = executable.stat().st_size
    if args.expected_heroes:
        expected = sorted(args.expected_heroes.split(","))
        report["expected_heroes_match"] = report["checks"].get("provided_image_ocr") == expected
        report["success"] = report["success"] and report["expected_heroes_match"]
    (artifacts / "exe-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if result.returncode or not report.get("success") or len(report["isolated_directory_files"]) != 1:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
