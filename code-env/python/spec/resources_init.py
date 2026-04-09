import hashlib
import json
import os
import shutil
import stat
import subprocess
import urllib.request
from platform import libc_ver

from dataiku.code_env_resources import clear_all_env_vars, set_env_path

KIJI_REPO = "dataiku/kiji-proxy"
KIJI_TAG = "latest"  # "latest" or a tag from https://github.com/dataiku/kiji-proxy/tags
DEST_DIR_NAME = "kiji-proxy"


def resolve_tag_version_and_repo(repo, tag):
    """
    `kiji_tag` can be either 'latest', or a tag from github. If the tag
    is 'latest', then we find and return the latest tag.

    The current Kiji release convention is that tags start with the
    character 'v' and versions do not (e.g. v0.4.9 vs 0.4.9).
    """
    if tag == "latest":
        latest_release_url = f"https://api.github.com/repos/{repo}/releases/latest"
        with urllib.request.urlopen(latest_release_url) as r:
            payload = json.loads(r.read().decode("utf-8"))
        tag = payload["tag_name"]

    version = tag[1:]  # remove leaving 'v' from tag
    return tag, version


def download_file(url, path):
    with urllib.request.urlopen(url) as response, open(path, "wb") as output:
        shutil.copyfileobj(response, output)


def verify_sha256(file_path, checksum_path):
    expected = open(checksum_path, "r").read().strip().split()[0]

    digest = hashlib.sha256()
    with open(file_path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)

    actual = digest.hexdigest()
    if actual != expected:
        raise ValueError("Checksum mismatch for {}".format(file_path))


def make_executable(path):
    current_mode = os.stat(path).st_mode
    os.chmod(path, current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main():
    # Clear environment variables defined in previous runs
    clear_all_env_vars()

    # Clear and/or create Kiji home directory
    set_env_path("KIJI_HOME", DEST_DIR_NAME)
    dest_dir = os.environ["KIJI_HOME"]

    if os.path.isdir(dest_dir):
        shutil.rmtree(dest_dir)
    os.makedirs(dest_dir)

    # Determine download URLs
    tag, version = resolve_tag_version_and_repo(KIJI_REPO, KIJI_TAG)
    archive_name = f"kiji-privacy-proxy-{version}-linux-amd64.tar.gz"
    base_url = f"https://github.com/{KIJI_REPO}/releases/download/{tag}"
    archive_url = f"{base_url}/{archive_name}"
    checksum_url = "{}.sha256".format(archive_url)

    # Download Kiji and verify checksum
    print(f"Downloading Kiji proxy {tag} from KIJI_REPO")

    archive_path = os.path.join(dest_dir, archive_name)
    checksum_path = archive_path + ".sha256"

    download_file(archive_url, archive_path)
    download_file(checksum_url, checksum_path)
    verify_sha256(archive_path, checksum_path)

    # Extract and make executable
    subprocess.check_call(
        ["tar", "xzf", archive_path, "-C", dest_dir, "--strip-components=1"]
    )
    os.remove(archive_path)
    os.remove(checksum_path)

    make_executable(os.path.join(dest_dir, "bin", "kiji-proxy"))
    make_executable(os.path.join(dest_dir, "run.sh"))

    # Set ONNX environment variables
    set_env_path("LD_LIBRARY_PATH", f"{DEST_DIR_NAME}/lib")
    set_env_path(
        "ONNXRUNTIME_SHARED_LIBRARY_PATH",
        f"{DEST_DIR_NAME}/lib/libonnxruntime.so.1.24.2",
    )

    print("Installed Kiji proxy {} to {}".format(version, dest_dir))


if __name__ == "__main__":
    main()
