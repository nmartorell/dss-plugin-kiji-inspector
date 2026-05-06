import hashlib
import os
import shutil
import stat
import tarfile
import tempfile

import requests
from dataiku.code_env_resources import clear_all_env_vars, set_env_path, set_env_var

KIJI_REPO = "dataiku/kiji-proxy"
KIJI_TAG = "latest"  # "latest" or a tag from https://github.com/dataiku/kiji-proxy/tags
USE_CUSTOM_PII_MODEL = False


def resolve_kiji_release_tag(repo, tag):
    """
    `tag` can be either 'latest', or a tag from GitHub:
       https://github.com/dataiku/kiji-proxy/tags

    If `tag` is 'latest', we retrieve the latest release tag.
    """
    if tag == "latest":
        latest_release_url = f"https://api.github.com/repos/{repo}/releases/latest"
        response = requests.get(latest_release_url, timeout=30)
        response.raise_for_status()

        payload = response.json()
        tag = payload.get("tag_name")
        if tag is None:
            raise RuntimeError(f"GitHub release response for {repo} did not include a tag_name.")

    return tag


def download_file(url, path):
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with open(path, "wb") as output:
            shutil.copyfileobj(response.raw, output)


def verify_sha256(file_path, checksum_path):
    with open(checksum_path, "r") as checksum_stream:
        expected = checksum_stream.read().strip().split()[0]

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


def find_onnxruntime_shared_library(lib_dir):
    for name in os.listdir(lib_dir):
        if name.startswith("libonnxruntime.so."):
            return name

    raise RuntimeError(f"No onnxruntime shared library found in {lib_dir}.")


def main():
    # Clear environment variables defined in previous runs
    clear_all_env_vars()

    # Define KIJI_HOME directory
    set_env_path("KIJI_HOME", "kiji-proxy")
    kiji_home = os.environ["KIJI_HOME"]

    # Resolve Kiji tag and version
    tag = resolve_kiji_release_tag(KIJI_REPO, KIJI_TAG)
    version = tag.lstrip("v")  # remove leading 'v' from tag (if present)

    # Download Kiji and verify checksum
    kiji_dir_name = f"kiji-privacy-proxy-{version}-linux-amd64"
    kiji_proxy_path = os.path.join(kiji_home, kiji_dir_name, "bin", "kiji-proxy")

    if os.path.isfile(kiji_proxy_path):
        print(f"Kiji proxy binary already present at {kiji_proxy_path}")
    else:
        print(f"Downloading Kiji proxy {tag} from {KIJI_REPO}")

        # Clear downloads from previous runs
        if os.path.isdir(kiji_home):
            shutil.rmtree(kiji_home)
        os.makedirs(kiji_home)

        # Download proxy tarball and checksum
        archive_name = kiji_dir_name + ".tar.gz"
        base_url = f"https://github.com/{KIJI_REPO}/releases/download/{tag}"
        archive_url = f"{base_url}/{archive_name}"
        checksum_url = f"{archive_url}.sha256"

        with tempfile.TemporaryDirectory(prefix="kiji-proxy-download-") as tmp_dir:
            archive_path = os.path.join(tmp_dir, archive_name)
            checksum_path = archive_path + ".sha256"

            download_file(archive_url, archive_path)
            download_file(checksum_url, checksum_path)
            verify_sha256(archive_path, checksum_path)

            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=kiji_home)

        make_executable(kiji_proxy_path)

    set_env_path("KIJI_PROXY", os.path.join("kiji-proxy", kiji_dir_name, "bin", "kiji-proxy"))

    # Set proxy environment variables
    lib_dir = os.path.join(kiji_home, kiji_dir_name, "lib")
    onnxruntime_shared_library = find_onnxruntime_shared_library(lib_dir)

    set_env_path("LD_LIBRARY_PATH", os.path.join(kiji_dir_name, "lib"))
    set_env_path(
        "ONNXRUNTIME_SHARED_LIBRARY_PATH",
        os.path.join(kiji_dir_name, "lib", onnxruntime_shared_library),
    )
    set_env_var("TRANSPARENT_PROXY_ENABLED", "False")

    if USE_CUSTOM_PII_MODEL:
        set_env_path("ONNX_MODEL_DIRECTORY", "custom-pii-model")
        custom_pii_model = os.environ["ONNX_MODEL_DIRECTORY"]
        os.makedirs(custom_pii_model, exist_ok=True)

    print(f"Installed Kiji proxy {version} to {os.path.join(kiji_home, kiji_dir_name)}")


if __name__ == "__main__":
    main()
