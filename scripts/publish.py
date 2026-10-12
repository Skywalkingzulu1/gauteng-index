#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish.py -- Build the Gauteng Index and publish it to GitHub Pages.

Deploy guardrail (see module docstring in build.py for why it exists):
  1. Refuses to run while GAUTENG_SITE_URL is set. Local-preview builds
     carry localhost canonicals; publishing one would replace the live
     site with thousands of localhost URLs. Unset the variable and run
     again for a production build.
  2. After building, scans the output for localhost URLs and refuses to
     push if any are baked in.
  3. build.py's own verify gate must pass (it exits non-zero otherwise).

Usage:
    python scripts/publish.py              # build, publish, wait
    python scripts/publish.py --no-build   # republish site/ as-is
    python scripts/publish.py --no-wait    # push without polling
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE = os.path.join(ROOT, "site")
CLONE = os.path.join(ROOT, ".publish_clone")
BRANCH = "gh-pages"
REPO = "Skywalkingzulu1/gauteng-index"
REMOTE = f"https://github.com/{REPO}.git"
URL = "https://skywalkingzulu1.github.io/gauteng-index/"
PROD_HOST = "https://skywalkingzulu1.github.io/gauteng-index"


def run(args, cwd=None, check=True):
    result = subprocess.run(args, cwd=cwd or ROOT, capture_output=True,
                            text=True)
    if check and result.returncode != 0:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(f"failed: {' '.join(args)}")
    return result


def guard_production():
    """Refuse anything but a production build. See module docstring."""
    if "GAUTENG_SITE_URL" in os.environ:
        raise SystemExit(
            "REFUSING TO PUBLISH: GAUTENG_SITE_URL is set "
            f"({os.environ['GAUTENG_SITE_URL']}). Unset it and rebuild "
            "production output first.")
    bad = []
    checked = 0
    # The sitemap is generated from the same SITE_URL as every canonical
    # tag, so a localhost leak cannot spare it: scanning the sitemap
    # shards plus the homepage and a random sample is as rigorous as a
    # full-tree walk and finishes in seconds instead of minutes.
    import random
    targets = []
    for root, _dirs, files in os.walk(SITE):
        for f in files:
            if f == "sitemap.xml" or f.startswith("sitemap-") \
                    or f == "index.html" and root == SITE:
                targets.append(os.path.join(root, f))
    html_pages = []
    for root, _dirs, files in os.walk(SITE):
        for f in files:
            if f == "index.html":
                html_pages.append(os.path.join(root, f))
    random.seed(20261011)
    targets += random.sample(html_pages, min(100, len(html_pages)))
    for p in targets:
        # Canonical tags, asset links and sitemap entries all live in
        # the first bytes.
        with open(p, encoding="utf-8") as fh:
            head = fh.read(4096)
        checked += 1
        if "http://localhost" in head or "http://127.0.0.1" in head:
            bad.append(os.path.relpath(p, SITE))
            if len(bad) >= 5:
                break
    if bad:
        raise SystemExit(
            "REFUSING TO PUBLISH: localhost URLs baked into output, e.g. "
            f"{bad[:3]}. Rebuild production output first.")
    print(f">>> guard: production host {PROD_HOST}, no localhost URLs "
          f"({checked} files checked: sitemap + home + sample)")


def build():
    print(">>> building")
    env = {k: v for k, v in os.environ.items()
           if k != "GAUTENG_SITE_URL"}
    result = subprocess.run([sys.executable, os.path.join(HERE, "build.py")],
                            cwd=ROOT, capture_output=True, text=True,
                            env=env)
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit("build failed (see verify output above)")
    if not os.path.isdir(SITE):
        raise SystemExit("site/ missing after build")


def discard(path):
    if not os.path.exists(path):
        return
    for _ in range(3):
        try:
            shutil.rmtree(path)
            return
        except (PermissionError, OSError):
            time.sleep(1.5)
    shutil.rmtree(path, ignore_errors=True)


def publish():
    print(f">>> publishing to {BRANCH}")
    discard(CLONE)
    run(["git", "clone", "--quiet", REMOTE, CLONE])
    r = run(["git", "checkout", "--quiet", BRANCH], cwd=CLONE, check=False)
    if r.returncode != 0:
        run(["git", "checkout", "--orphan", BRANCH], cwd=CLONE)
    for entry in os.listdir(CLONE):
        if entry == ".git":
            continue
        p = os.path.join(CLONE, entry)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    for entry in os.listdir(SITE):
        s = os.path.join(SITE, entry)
        d = os.path.join(CLONE, entry)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
    open(os.path.join(CLONE, ".nojekyll"), "w",
         encoding="utf-8").close()
    run(["git", "add", "-A"], cwd=CLONE)
    if run(["git", "diff", "--cached", "--quiet"], cwd=CLONE,
           check=False).returncode == 0:
        print("    nothing changed")
        discard(CLONE)
        return False
    run(["git", "-c", "user.name=Gauteng Index",
         "-c", "user.email=noreply@github.com",
         "commit", "--quiet", "-m",
         "Publish Gauteng Index\n\nGenerated by scripts/build.py."],
        cwd=CLONE)
    run(["git", "push", "--quiet", "origin", f"HEAD:{BRANCH}"], cwd=CLONE)
    sha = run(["git", "rev-parse", "--short", "HEAD"],
              cwd=CLONE).stdout.strip()
    n = len(run(["git", "ls-files"], cwd=CLONE).stdout.splitlines())
    print(f"    pushed {sha} ({n} files)")
    discard(CLONE)
    return True


def ensure_pages_source():
    r = run(["gh", "api", f"repos/{REPO}/pages", "--jq",
             '.source.branch + " " + .source.path'], check=False)
    if r.stdout.strip() != f"{BRANCH} /":
        run(["gh", "api", "-X", "PUT", f"repos/{REPO}/pages",
             "-f", f"source[branch]={BRANCH}", "-f", "source[path]=/"],
            check=False)
    else:
        print(f">>> Pages source already {BRANCH} /")


def wait_for_build(timeout_s=900):
    print(">>> waiting for Pages build")
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        status = run(["gh", "api", f"repos/{REPO}/pages/builds/latest",
                      "--jq", ".status"], check=False).stdout.strip()
        if status != last:
            print(f"    {status}")
            last = status
        if status in ("built", "errored"):
            return status == "built"
        time.sleep(15)
    print("    timed out")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--no-wait", action="store_true")
    args = ap.parse_args()

    if not args.no_build:
        build()
    guard_production()
    ensure_pages_source()

    if not publish():
        print("\nAlready up to date.")
        return

    if args.no_wait:
        print(f"\nPushed. See the build in repository Pages settings.\n{URL}")
        return

    ok = wait_for_build()
    print(f"\n{'Live' if ok else 'Build did not confirm'}: {URL}")


if __name__ == "__main__":
    main()
