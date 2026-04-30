import hashlib
import os
import shutil
import stat
import subprocess

import requests
from dataiku.code_env_resources import clear_all_env_vars, set_env_path, set_env_var

KIJI_REPO = "dataiku/kiji-proxy"
KIJI_TAG = "latest"  # "latest" or a tag from https://github.com/dataiku/kiji-proxy/tags


def resolve_kiji_release_tag(repo, tag):
    """
    `tag` can be either 'latest', or a tag from github:
       https://github.com/dataiku/kiji-proxy/tags

    If `tag` 'latest', then we retrieve the latest release tag.
    By convention, tags start with the letter 'v', e.g. 'v0.5.1'.
    """
    if tag == "latest":
        latest_release_url = f"https://api.github.com/repos/{repo}/releases/latest"
        payload = requests.get(latest_release_url, timeout=30).json()
        tag = payload["tag_name"]

    return tag


def download_file(url, path):
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with open(path, "wb") as output:
            shutil.copyfileobj(response.raw, output)


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

    # Create Kiji home directory (and clear contents from previous runs)
    set_env_path("KIJI_HOME", "kiji-proxy")
    dest_dir = os.environ["KIJI_HOME"]

    if os.path.isdir(dest_dir):
        shutil.rmtree(dest_dir)
    os.makedirs(dest_dir)

    # Construct Kiji download URLs
    tag = resolve_kiji_release_tag(KIJI_REPO, KIJI_TAG)
    version = tag.lstrip("v")  # remove leading 'v' from tag (if present)

    base_url = f"https://github.com/{KIJI_REPO}/releases/download/{tag}"
    archive_name = f"kiji-privacy-proxy-{version}-linux-amd64.tar.gz"

    archive_url = f"{base_url}/{archive_name}"
    checksum_url = f"{archive_url}.sha256"

    # Download Kiji and verify checksum
    print(f"Downloading Kiji proxy {tag} from {KIJI_REPO}")

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
    set_env_var("LD_LIBRARY_PATH", f"{dest_dir}/lib")
    set_env_var(
        "ONNXRUNTIME_SHARED_LIBRARY_PATH",
        f"{dest_dir}/lib/libonnxruntime.so.1.24.2",
    )
    set_env_var("TRANSPARENT_PROXY_ENABLED", "False")

    print("Installed Kiji proxy {} to {}".format(version, dest_dir))


if __name__ == "__main__":
    main()
