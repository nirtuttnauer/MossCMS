#!/usr/bin/env python3
"""Build a source snapshot and measure isolated Docker fixtures; never deploy the normal CMS."""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def snapshot(root, target):
    paths = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=root).split(b"\0")
    checksum = hashlib.sha256()
    for raw in sorted(set(paths)):
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        source = root / relative
        if source.is_symlink():
            raise ValueError(f"Source snapshot refuses symlinks: {relative}")
        if not source.is_file():
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        checksum.update(raw + b"\0" + destination.read_bytes())
    return checksum.hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def memory_bytes(value):
    number, unit = re.fullmatch(r"([0-9.]+)\s*(B|KiB|MiB|GiB)", value.strip()).groups()
    return int(float(number) * {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}[unit])


def resource_summary(samples):
    output = {}
    for sample in samples:
        for value in sample["containers"]:
            service = value["Name"].rsplit("-", 2)[-2]
            current = output.setdefault(service, {"peakMemoryBytes": 0, "peakCpuPercent": 0, "samples": 0})
            current["peakMemoryBytes"] = max(current["peakMemoryBytes"], memory_bytes(value["MemUsage"].split("/")[0]))
            current["peakCpuPercent"] = max(current["peakCpuPercent"], float(value["CPUPerc"].rstrip("%")))
            current["samples"] += 1
    return output


def remove_fixture_volumes(project):
    """Remove only this disposable project's volumes, including the pre-recovery media."""
    if not re.fullmatch(r"moss-benchmark-[a-z0-9-]+", project):
        raise ValueError("Refusing to clean a non-benchmark project")
    names = subprocess.check_output(
        ["docker", "volume", "ls", "--filter", f"label=com.docker.compose.project={project}", "--format", "{{.Name}}"],
        text=True,
    ).splitlines()
    if not names:
        return
    volumes = json.loads(subprocess.check_output(["docker", "volume", "inspect", *names], text=True))
    if any(volume.get("Labels", {}).get("com.docker.compose.project") != project for volume in volumes):
        raise ValueError("Refusing to remove a volume owned by another project")
    subprocess.run(["docker", "volume", "rm", *names], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sizes", type=int, nargs="+", choices=[1000, 10000, 50000, 100000], default=[1000, 10000, 50000, 100000]
    )
    parser.add_argument("--seconds", type=int, default=60, help="Measurement duration for the smaller fixtures.")
    parser.add_argument(
        "--sustain-seconds", type=int, default=1800, help="Measurement duration for the largest selected fixture."
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="A new evidence directory, outside ignored private backups."
    )
    args = parser.parse_args()
    args.sizes = sorted(set(args.sizes))
    if not 1 <= args.seconds <= 86400 or not 1 <= args.sustain_seconds <= 86400:
        parser.error("Durations must be 1–86400 seconds.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="moss-benchmark-") as private:
        private_root = Path(private)
        copied = private_root / "source"
        copied.mkdir()
        digest = snapshot(ROOT, copied)
        project = private_root.name.replace("_", "-")
        image = f"mosscms:benchmark-{digest[:12]}"
        env = {
            **os.environ,
            "COMPOSE_FILE": str(copied / "compose.benchmark.yaml"),
            "COMPOSE_PROJECT_NAME": project,
            "MOSS_BENCHMARK_IMAGE": image,
            "MOSS_BENCHMARK_RESULTS": str(output),
        }
        # Ignore the operator's normal backend selection and Compose overrides.
        for key in ("COMPOSE_PROFILES", "MOSS_BENCHMARK_DATABASE", "MOSS_BENCHMARK_MEDIA"):
            env.pop(key, None)

        def compose(*command, **kwargs):
            return subprocess.run(
                ["docker", "compose", "--env-file", "/dev/null", *command], cwd=copied, env=env, check=True, **kwargs
            )

        def action(name, filename, *options):
            compose("run", "--rm", "-T", "--no-deps", "benchmark", name, "--output", f"/results/{filename}", *options)
            return read_json(output / filename)

        metadata = {
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "sourceCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "sourceSnapshotSha256": digest,
            "host": platform.platform(),
            "architecture": platform.machine(),
            "resourceLimits": {"app": "2 CPUs / 4 GiB", "db": "2 CPUs / 4 GiB"},
            "conditions": "Local Docker Desktop; shared host; container CPU/memory caps are not dedicated cloud hardware",
            "runs": [],
            "complete": False,
        }
        (output / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
        build_log = output / "build.log"
        with build_log.open("w") as log:
            subprocess.run(
                ["docker", "build", "--tag", image, "--label", f"moss.benchmark.source={digest}", "."],
                cwd=copied,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
        metadata["imageId"] = subprocess.check_output(
            ["docker", "image", "inspect", image, "--format", "{{.Id}}"], text=True
        ).strip()
        metadata["docker"] = json.loads(
            subprocess.check_output(["docker", "info", "--format", "{{json .}}"], text=True)
        )
        # Save resource/version information, not Docker registry configuration or host paths.
        metadata["docker"] = {
            k: metadata["docker"].get(k) for k in ("ServerVersion", "Architecture", "NCPU", "MemTotal", "KernelVersion")
        }
        try:
            for size in args.sizes:
                print(f"Benchmark: seeding {size:,} entries", flush=True)
                compose("up", "-d", "--wait", "db")
                fixture = action("seed", f"fixture-{size}.json", "--size", str(size))
                compose("up", "-d", "--wait", "--no-deps", "app")
                seconds = args.sustain_seconds if size == max(args.sizes) else args.seconds
                commands = [
                    "docker",
                    "compose",
                    "--env-file",
                    "/dev/null",
                    "run",
                    "--rm",
                    "-T",
                    "--no-deps",
                    "benchmark",
                    "run",
                    "--seconds",
                    str(seconds),
                    "--output",
                    f"/results/load-{size}.json",
                ]
                samples = []
                with (output / f"run-{size}.log").open("w") as log:
                    process = subprocess.Popen(commands, cwd=copied, env=env, stdout=log, stderr=subprocess.STDOUT)
                    try:
                        ids = compose("ps", "-q", "app", "db", capture_output=True, text=True).stdout.split()
                        while process.poll() is None:
                            stats = subprocess.check_output(
                                ["docker", "stats", "--no-stream", "--format", "{{json .}}", *ids], text=True
                            )
                            samples.append(
                                {"at": time.time(), "containers": [json.loads(line) for line in stats.splitlines()]}
                            )
                            if len(samples) % 6 == 0:
                                print(f"Benchmark: {size:,} entries, {len(samples)} resource samples", flush=True)
                            try:
                                process.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                pass
                    finally:
                        if process.poll() is None:
                            process.terminate()
                            process.wait(timeout=15)
                    if process.returncode != 0:
                        raise RuntimeError(f"Load runner failed; inspect run-{size}.log")
                (output / f"resources-{size}.json").write_text(json.dumps(samples, indent=2) + "\n")
                load = read_json(output / f"load-{size}.json")
                checks = action("verify", f"checks-{size}.json")
                run = {
                    "size": size,
                    "fixture": fixture,
                    "checks": checks,
                    "load": load,
                    "resources": resource_summary(samples),
                }
                if size == max(args.sizes):
                    action("prepare-schedule", "schedule.json")
                    compose("stop", "app")
                    before = action("fingerprint", "before-recovery.json")
                    backup_dir = private_root / "backup"
                    subprocess.run(
                        [sys.executable, str(copied / "scripts/backup.py"), "--directory", str(backup_dir)],
                        cwd=copied,
                        env=env,
                        check=True,
                    )
                    compose("exec", "-T", "db", "createdb", "-U", "benchmark", "moss_benchmark_recovery")
                    recovery_started = time.perf_counter()
                    backup_stamp = datetime.strptime(next(backup_dir.glob("*.dump")).stem, "%Y%m%dT%H%M%SZ").replace(
                        tzinfo=timezone.utc
                    )
                    subprocess.run(
                        [
                            sys.executable,
                            str(copied / "scripts/restore.py"),
                            str(next(backup_dir.glob("*.dump"))),
                            "--target",
                            "moss_benchmark_recovery",
                            "--confirm-target",
                            "moss_benchmark_recovery",
                        ],
                        cwd=copied,
                        env=env,
                        check=True,
                    )
                    env["MOSS_BENCHMARK_DATABASE"] = "moss_benchmark_recovery"
                    env["MOSS_BENCHMARK_MEDIA"] = "recovered_media"
                    subprocess.run(
                        [
                            sys.executable,
                            str(copied / "scripts/restore_media.py"),
                            str(next(backup_dir.glob("*.media.tar.gz"))),
                            "--confirm-empty-volume",
                        ],
                        cwd=copied,
                        env=env,
                        check=True,
                    )
                    after = action("fingerprint", "after-recovery.json")
                    assert before == after, "Restored database or media differs from the captured backup"
                    compose("up", "-d", "--wait", "--no-deps", "app")
                    captured_schedule = action("verify-schedule", "recovered-schedule.json")
                    recovered_checks = action("verify", "recovered-checks.json")
                    recovered_history = action("verify-history", "recovered-history.json")
                    compose("restart", "app")
                    compose("up", "-d", "--wait", "--no-deps", "app")
                    restart_checks = action("verify", "restart-checks.json")
                    restarted_schedule = action("verify-schedule", "restarted-schedule.json")
                    compose("run", "--rm", "-T", "--no-deps", "delivery-client")
                    run["recovery"] = {
                        "seconds": time.perf_counter() - recovery_started,
                        "fingerprintsMatch": True,
                        "afterRestore": recovered_checks,
                        "afterRestart": restart_checks,
                        "backupBytes": sum(p.stat().st_size for p in backup_dir.iterdir()),
                        "capturedSchedule": captured_schedule,
                        "afterSecondRestart": restarted_schedule,
                        "historicalRestore": recovered_history,
                        "deliveryClient": read_json(output / "delivery-client-checks.json"),
                        "backupCapturedAtUtc": backup_stamp.isoformat(),
                        "backupAgeAtVerificationSeconds": (datetime.now(timezone.utc) - backup_stamp).total_seconds(),
                    }
                metadata["runs"].append(run)
                (output / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
                compose("down", "--volumes")
            metadata["complete"] = True
        finally:
            compose("down", "--volumes", "--remove-orphans")
            remove_fixture_volumes(project)
            metadata["finishedAt"] = datetime.now(timezone.utc).isoformat()
            (output / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(f"Benchmark evidence: {output}", flush=True)


if __name__ == "__main__":
    main()
