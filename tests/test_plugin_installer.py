"""
Unit tests for app/plugin_installer.py — local-plugin code-download installer.

Pure-logic tests with fixture archives and a tiny local HTTP server (stdlib
only). Mirrors test_plugin_signing.py's inject_test_keys fixture style for
mint_download_token, and test_remote_plugins.py's pytest.importorskip style
for the FastAPI/httpx dependency.

Run with:
    pytest tests/test_plugin_installer.py -v
"""
from __future__ import annotations

import io
import stat
import tarfile
import threading
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("yaml")

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_rsa_keypair():
    """Generate a throwaway RSA-2048 key pair for testing."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    pub_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return priv_pem, pub_pem


@pytest.fixture(autouse=True)
def inject_test_keys(test_rsa_keypair, monkeypatch):
    """Inject a test key pair so mint_download_token doesn't touch the filesystem."""
    priv_pem, _ = test_rsa_keypair
    monkeypatch.setenv("OPAMA_INSTANCE_PRIVATE_KEY", priv_pem)
    monkeypatch.setenv("OPAMA_INSTANCE_ID", str(uuid.uuid4()))

    import app.plugin_signing as ps
    ps._private_pem = None
    ps._public_pem = None
    ps._instance_id = None
    yield
    ps._private_pem = None
    ps._public_pem = None
    ps._instance_id = None


# ---------------------------------------------------------------------------
# mint_download_token
# ---------------------------------------------------------------------------

class TestMintDownloadToken:

    def test_returns_jwt_string(self):
        from app.plugin_installer import mint_download_token
        token = mint_download_token("my_plugin", "premium")
        assert isinstance(token, str)
        assert token.count(".") == 2

    def test_claims_shape(self, test_rsa_keypair):
        from app.plugin_installer import mint_download_token
        from app.plugin_signing import get_instance_id
        _, pub_pem = test_rsa_keypair
        token = mint_download_token("my_plugin", "premium")
        payload = jwt.decode(token, pub_pem, algorithms=["RS256"])
        assert payload["plugin_id"] == "my_plugin"
        assert payload["tier"] == "premium"
        assert payload["iss"] == "opama"
        assert payload["instance_id"] == get_instance_id()

    def test_excludes_user_id_and_customer(self):
        from app.plugin_installer import mint_download_token
        token = mint_download_token("my_plugin", "premium")
        payload = jwt.decode(token, options={"verify_signature": False}, algorithms=["RS256"])
        assert "user_id" not in payload
        assert "customer" not in payload

    def test_default_ttl_is_15_minutes(self):
        from app.plugin_installer import mint_download_token, DOWNLOAD_TOKEN_TTL_SECONDS
        assert DOWNLOAD_TOKEN_TTL_SECONDS == 15 * 60
        token = mint_download_token("p", "free")
        payload = jwt.decode(token, options={"verify_signature": False}, algorithms=["RS256"])
        assert 898 <= (payload["exp"] - payload["iat"]) <= 902

    def test_custom_ttl(self):
        from app.plugin_installer import mint_download_token
        token = mint_download_token("p", "free", ttl_seconds=30)
        payload = jwt.decode(token, options={"verify_signature": False}, algorithms=["RS256"])
        assert 28 <= (payload["exp"] - payload["iat"]) <= 32

    def test_distinct_shape_from_sign_plugin_token(self):
        from app.plugin_installer import mint_download_token
        from app.plugin_signing import sign_plugin_token
        download_tok = mint_download_token("p", "premium")
        proxy_tok = sign_plugin_token("user_1", "p")
        d = jwt.decode(download_tok, options={"verify_signature": False}, algorithms=["RS256"])
        p = jwt.decode(proxy_tok, options={"verify_signature": False}, algorithms=["RS256"])
        assert "tier" in d and "user_id" not in d
        assert "user_id" in p and "tier" not in p


# ---------------------------------------------------------------------------
# validate_local_manifest
# ---------------------------------------------------------------------------

class TestValidateLocalManifest:

    def _base_manifest(self, **overrides):
        data = {
            "id": "my_plugin",
            "name": "My Plugin",
            "download_url": "https://example.com/my_plugin.tar.gz",
            "router_module": "my_plugin.router",
        }
        data.update(overrides)
        return data

    def test_valid_manifest_passes(self):
        from app.plugin_installer import validate_local_manifest
        validate_local_manifest(self._base_manifest(), "my_plugin")  # no raise

    def test_missing_download_url(self):
        from fastapi import HTTPException
        from app.plugin_installer import validate_local_manifest
        data = self._base_manifest()
        del data["download_url"]
        with pytest.raises(HTTPException) as exc_info:
            validate_local_manifest(data, "my_plugin")
        assert exc_info.value.status_code == 422
        assert "download_url" in str(exc_info.value.detail)

    def test_missing_router_module(self):
        from fastapi import HTTPException
        from app.plugin_installer import validate_local_manifest
        data = self._base_manifest()
        del data["router_module"]
        with pytest.raises(HTTPException) as exc_info:
            validate_local_manifest(data, "my_plugin")
        assert exc_info.value.status_code == 422
        assert "router_module" in str(exc_info.value.detail)

    def test_model_modules_rejected(self):
        from fastapi import HTTPException
        from app.plugin_installer import validate_local_manifest
        data = self._base_manifest(model_modules=["my_plugin.models"])
        with pytest.raises(HTTPException) as exc_info:
            validate_local_manifest(data, "my_plugin")
        assert exc_info.value.status_code == 422
        assert "model_modules" in str(exc_info.value.detail)

    def test_empty_model_modules_allowed(self):
        from app.plugin_installer import validate_local_manifest
        validate_local_manifest(self._base_manifest(model_modules=[]), "my_plugin")  # no raise

    def test_id_mismatch_rejected(self):
        from fastapi import HTTPException
        from app.plugin_installer import validate_local_manifest
        data = self._base_manifest(id="other_plugin")
        with pytest.raises(HTTPException) as exc_info:
            validate_local_manifest(data, "my_plugin")
        assert exc_info.value.status_code == 422
        assert "my_plugin" in str(exc_info.value.detail)

    def test_missing_id_allowed(self):
        from app.plugin_installer import validate_local_manifest
        data = self._base_manifest()
        del data["id"]
        validate_local_manifest(data, "my_plugin")  # no raise

    def test_router_attr_override_rejected(self):
        from fastapi import HTTPException
        from app.plugin_installer import validate_local_manifest
        data = self._base_manifest(router_attr="custom_router")
        with pytest.raises(HTTPException) as exc_info:
            validate_local_manifest(data, "my_plugin")
        assert exc_info.value.status_code == 422

    def test_router_attr_default_router_allowed(self):
        from app.plugin_installer import validate_local_manifest
        validate_local_manifest(self._base_manifest(router_attr="router"), "my_plugin")  # no raise


# ---------------------------------------------------------------------------
# _safe_member_dest — path-traversal guard
# ---------------------------------------------------------------------------

class TestSafeMemberDest:

    def test_rejects_empty_name(self, tmp_path):
        from app.plugin_installer import _safe_member_dest
        with pytest.raises(ValueError):
            _safe_member_dest("", tmp_path)

    def test_rejects_nul_byte(self, tmp_path):
        from app.plugin_installer import _safe_member_dest
        with pytest.raises(ValueError):
            _safe_member_dest("evil\0.txt", tmp_path)

    def test_rejects_absolute_path(self, tmp_path):
        from app.plugin_installer import _safe_member_dest
        with pytest.raises(ValueError):
            _safe_member_dest("/etc/passwd", tmp_path)

    def test_rejects_parent_traversal(self, tmp_path):
        from app.plugin_installer import _safe_member_dest
        with pytest.raises(ValueError):
            _safe_member_dest("../evil.txt", tmp_path)

    def test_rejects_sibling_directory_bypass(self, tmp_path):
        """A member named '../dest_root_evil/x' must not pass a string-prefix check."""
        from app.plugin_installer import _safe_member_dest
        dest_root = tmp_path / "dest_root"
        dest_root.mkdir()
        with pytest.raises(ValueError):
            _safe_member_dest("../dest_root_evil/x", dest_root)

    def test_allows_normal_relative_path(self, tmp_path):
        from app.plugin_installer import _safe_member_dest
        dest_root = tmp_path / "dest_root"
        dest_root.mkdir()
        target = _safe_member_dest("pkg/file.py", dest_root)
        assert target == (dest_root / "pkg" / "file.py").resolve()

    def test_allows_root_itself(self, tmp_path):
        from app.plugin_installer import _safe_member_dest
        dest_root = tmp_path / "dest_root"
        dest_root.mkdir()
        target = _safe_member_dest(".", dest_root)
        assert target == dest_root.resolve()


# ---------------------------------------------------------------------------
# _extract_tar
# ---------------------------------------------------------------------------

def _make_tar(tmp_path, members, name="archive.tar.gz"):
    """members: list of (name, kind, content_bytes_or_None, extra_attrs dict)"""
    archive_path = tmp_path / name
    with tarfile.open(archive_path, "w:gz") as tar:
        for member_name, kind, content, extra in members:
            info = tarfile.TarInfo(name=member_name)
            extra = extra or {}
            for k, v in extra.items():
                if k == "linkname":
                    continue
                setattr(info, k, v)
            if kind == "file":
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
            elif kind == "dir":
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = extra.get("linkname", "target")
                tar.addfile(info)
            elif kind == "hardlink":
                info.type = tarfile.LNKTYPE
                info.linkname = extra.get("linkname", "target")
                tar.addfile(info)
            elif kind == "device":
                info.type = tarfile.CHRTYPE
                tar.addfile(info)
    return archive_path


class TestExtractTar:

    def test_extracts_regular_files(self, tmp_path):
        from app.plugin_installer import _extract_tar
        archive = _make_tar(tmp_path, [
            ("plugin.yaml", "file", b"id: x\n", None),
            ("pkg/__init__.py", "file", b"", None),
        ])
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        _extract_tar(archive, extract_dir)
        assert (extract_dir / "plugin.yaml").read_bytes() == b"id: x\n"
        assert (extract_dir / "pkg" / "__init__.py").exists()

    def test_rejects_symlink_member(self, tmp_path):
        from app.plugin_installer import _extract_tar
        archive = _make_tar(tmp_path, [("evil_link", "symlink", None, {"linkname": "/etc/passwd"})])
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with pytest.raises(ValueError, match="unsafe member type"):
            _extract_tar(archive, extract_dir)

    def test_rejects_hardlink_member(self, tmp_path):
        from app.plugin_installer import _extract_tar
        archive = _make_tar(tmp_path, [("evil_link", "hardlink", None, {"linkname": "plugin.yaml"})])
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with pytest.raises(ValueError, match="unsafe member type"):
            _extract_tar(archive, extract_dir)

    def test_rejects_device_member(self, tmp_path):
        from app.plugin_installer import _extract_tar
        archive = _make_tar(tmp_path, [("evil_dev", "device", None, None)])
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with pytest.raises(ValueError, match="unsafe member type"):
            _extract_tar(archive, extract_dir)

    def test_rejects_path_traversal_member(self, tmp_path):
        from app.plugin_installer import _extract_tar
        archive = _make_tar(tmp_path, [("../evil.txt", "file", b"x", None)])
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with pytest.raises(ValueError, match="path traversal"):
            _extract_tar(archive, extract_dir)

    def test_member_count_cap(self, tmp_path, monkeypatch):
        import app.plugin_installer as pi
        monkeypatch.setattr(pi, "MAX_MEMBERS", 2)
        archive = _make_tar(tmp_path, [
            ("a.txt", "file", b"a", None),
            ("b.txt", "file", b"b", None),
            ("c.txt", "file", b"c", None),
        ])
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with pytest.raises(ValueError, match="too many entries"):
            pi._extract_tar(archive, extract_dir)

    def test_extracted_size_cap(self, tmp_path, monkeypatch):
        import app.plugin_installer as pi
        monkeypatch.setattr(pi, "MAX_EXTRACTED_BYTES", 10)
        archive = _make_tar(tmp_path, [("big.txt", "file", b"x" * 100, None)])
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with pytest.raises(ValueError, match="extracted-size limit"):
            pi._extract_tar(archive, extract_dir)

    def test_strips_permission_bits(self, tmp_path):
        from app.plugin_installer import _extract_tar, _EXTRACTED_FILE_MODE
        archive = _make_tar(tmp_path, [("script.sh", "file", b"#!/bin/sh\n", {"mode": 0o4777})])
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        _extract_tar(archive, extract_dir)
        mode = stat.S_IMODE((extract_dir / "script.sh").stat().st_mode)
        assert mode == _EXTRACTED_FILE_MODE


# ---------------------------------------------------------------------------
# _extract_zip
# ---------------------------------------------------------------------------

def _make_zip(tmp_path, members, name="archive.zip"):
    """members: list of (name, content_bytes)"""
    archive_path = tmp_path / name
    with zipfile.ZipFile(archive_path, "w") as zf:
        for member_name, content in members:
            zf.writestr(member_name, content or b"")
    return archive_path


class TestExtractZip:

    def test_extracts_regular_files(self, tmp_path):
        from app.plugin_installer import _extract_zip
        archive = _make_zip(tmp_path, [
            ("plugin.yaml", b"id: x\n"),
            ("pkg/__init__.py", b""),
        ])
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        _extract_zip(archive, extract_dir)
        assert (extract_dir / "plugin.yaml").read_bytes() == b"id: x\n"
        assert (extract_dir / "pkg" / "__init__.py").exists()

    def test_rejects_symlink_member(self, tmp_path):
        from app.plugin_installer import _extract_zip
        archive_path = tmp_path / "archive.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            info = zipfile.ZipInfo("evil_link")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "/etc/passwd")
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with pytest.raises(ValueError, match="unsafe member type"):
            _extract_zip(archive_path, extract_dir)

    def test_rejects_path_traversal_member(self, tmp_path):
        from app.plugin_installer import _extract_zip
        archive = _make_zip(tmp_path, [("../evil.txt", b"x")])
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with pytest.raises(ValueError, match="path traversal"):
            _extract_zip(archive, extract_dir)

    def test_member_count_cap(self, tmp_path, monkeypatch):
        import app.plugin_installer as pi
        monkeypatch.setattr(pi, "MAX_MEMBERS", 2)
        archive = _make_zip(tmp_path, [("a.txt", b"a"), ("b.txt", b"b"), ("c.txt", b"c")])
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with pytest.raises(ValueError, match="too many entries"):
            pi._extract_zip(archive, extract_dir)

    def test_extracted_size_cap(self, tmp_path, monkeypatch):
        import app.plugin_installer as pi
        monkeypatch.setattr(pi, "MAX_EXTRACTED_BYTES", 10)
        archive = _make_zip(tmp_path, [("big.txt", b"x" * 100)])
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with pytest.raises(ValueError, match="extracted-size limit"):
            pi._extract_zip(archive, extract_dir)

    def test_strips_permission_bits(self, tmp_path):
        from app.plugin_installer import _extract_zip, _EXTRACTED_FILE_MODE
        archive_path = tmp_path / "archive.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            info = zipfile.ZipInfo("script.sh")
            info.external_attr = 0o4777 << 16
            zf.writestr(info, "#!/bin/sh\n")
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        _extract_zip(archive_path, extract_dir)
        mode = stat.S_IMODE((extract_dir / "script.sh").stat().st_mode)
        assert mode == _EXTRACTED_FILE_MODE


# ---------------------------------------------------------------------------
# _safe_extract — format sniffing + cleanup-on-failure
# ---------------------------------------------------------------------------

class TestSafeExtract:

    def test_rejects_non_archive(self, tmp_path):
        from fastapi import HTTPException
        from app.plugin_installer import _safe_extract
        bogus = tmp_path / "bogus.bin"
        bogus.write_bytes(b"not an archive")
        with pytest.raises(HTTPException) as exc_info:
            _safe_extract(bogus, tmp_path)
        assert exc_info.value.status_code == 422
        assert "neither a valid tar nor zip" in exc_info.value.detail

    def test_wraps_value_error_as_422(self, tmp_path):
        from fastapi import HTTPException
        from app.plugin_installer import _safe_extract
        archive = _make_tar(tmp_path, [("../evil.txt", "file", b"x", None)])
        with pytest.raises(HTTPException) as exc_info:
            _safe_extract(archive, tmp_path)
        assert exc_info.value.status_code == 422

    def test_extracts_valid_tar(self, tmp_path):
        from app.plugin_installer import _safe_extract
        archive = _make_tar(tmp_path, [("plugin.yaml", "file", b"id: x\n", None)])
        extract_dir = _safe_extract(archive, tmp_path)
        assert (extract_dir / "plugin.yaml").exists()

    def test_extracts_valid_zip(self, tmp_path):
        from app.plugin_installer import _safe_extract
        archive = _make_zip(tmp_path, [("plugin.yaml", b"id: x\n")])
        extract_dir = _safe_extract(archive, tmp_path)
        assert (extract_dir / "plugin.yaml").exists()

    def test_cleans_up_extract_dir_on_failure(self, tmp_path):
        from fastapi import HTTPException
        from app.plugin_installer import _safe_extract
        archive = _make_tar(tmp_path, [("../evil.txt", "file", b"x", None)])
        with pytest.raises(HTTPException):
            _safe_extract(archive, tmp_path)
        leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".plugin-extract-")]
        assert leftovers == []


# ---------------------------------------------------------------------------
# _strip_wrapper_dir
# ---------------------------------------------------------------------------

class TestStripWrapperDir:

    def test_single_dir_wrapper_stripped(self, tmp_path):
        from app.plugin_installer import _strip_wrapper_dir
        extract_dir = tmp_path / "extract"
        wrapper = extract_dir / "repo-abc123"
        wrapper.mkdir(parents=True)
        (wrapper / "plugin.yaml").write_text("id: x\n")
        assert _strip_wrapper_dir(extract_dir) == wrapper

    def test_multiple_entries_not_stripped(self, tmp_path):
        from app.plugin_installer import _strip_wrapper_dir
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        (extract_dir / "plugin.yaml").write_text("id: x\n")
        (extract_dir / "pkg").mkdir()
        assert _strip_wrapper_dir(extract_dir) == extract_dir

    def test_single_file_not_stripped(self, tmp_path):
        from app.plugin_installer import _strip_wrapper_dir
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        (extract_dir / "plugin.yaml").write_text("id: x\n")
        assert _strip_wrapper_dir(extract_dir) == extract_dir


# ---------------------------------------------------------------------------
# _load_and_validate_extracted_manifest
# ---------------------------------------------------------------------------

class TestLoadAndValidateExtractedManifest:

    def test_missing_manifest(self, tmp_path):
        from fastapi import HTTPException
        from app.plugin_installer import _load_and_validate_extracted_manifest
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        with pytest.raises(HTTPException) as exc_info:
            _load_and_validate_extracted_manifest(package_dir, "my_plugin")
        assert exc_info.value.status_code == 422
        assert "plugin.yaml" in exc_info.value.detail

    def test_invalid_yaml(self, tmp_path):
        from fastapi import HTTPException
        from app.plugin_installer import _load_and_validate_extracted_manifest
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        (package_dir / "plugin.yaml").write_text("id: [unterminated")
        with pytest.raises(HTTPException) as exc_info:
            _load_and_validate_extracted_manifest(package_dir, "my_plugin")
        assert exc_info.value.status_code == 422

    def test_non_mapping_yaml(self, tmp_path):
        from fastapi import HTTPException
        from app.plugin_installer import _load_and_validate_extracted_manifest
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        (package_dir / "plugin.yaml").write_text("- a\n- b\n")
        with pytest.raises(HTTPException) as exc_info:
            _load_and_validate_extracted_manifest(package_dir, "my_plugin")
        assert exc_info.value.status_code == 422
        assert "mapping" in exc_info.value.detail

    def test_id_mismatch(self, tmp_path):
        from fastapi import HTTPException
        from app.plugin_installer import _load_and_validate_extracted_manifest
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        (package_dir / "plugin.yaml").write_text("id: other_plugin\nname: Other\n")
        with pytest.raises(HTTPException) as exc_info:
            _load_and_validate_extracted_manifest(package_dir, "my_plugin")
        assert exc_info.value.status_code == 422
        assert "spoofed" in exc_info.value.detail

    def test_valid_manifest(self, tmp_path):
        from app.plugin_installer import _load_and_validate_extracted_manifest
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        (package_dir / "plugin.yaml").write_text("id: my_plugin\nname: My Plugin\n")
        data = _load_and_validate_extracted_manifest(package_dir, "my_plugin")
        assert data["id"] == "my_plugin"
        assert data["name"] == "My Plugin"


# ---------------------------------------------------------------------------
# download_and_extract — end-to-end against a local fixture HTTP server
# ---------------------------------------------------------------------------

class _ArchiveHandler(BaseHTTPRequestHandler):
    archive_bytes: bytes = b""
    received_auth_headers: list[str] = []

    def do_GET(self):
        type(self).received_auth_headers.append(self.headers.get("Authorization", ""))
        body = type(self).archive_bytes
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args, **kwargs):
        pass


@pytest.fixture
def archive_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ArchiveHandler)
    _ArchiveHandler.received_auth_headers = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _build_tarball(plugin_id: str, *, wrapped: bool = False) -> bytes:
    buf = io.BytesIO()
    prefix = "repo-main/" if wrapped else ""
    files = {
        f"{prefix}plugin.yaml": f"id: {plugin_id}\nname: Test Plugin\nrouter_module: {plugin_id}.router\n",
        f"{prefix}__init__.py": "",
        f"{prefix}router.py": "from fastapi import APIRouter\nrouter = APIRouter()\n",
    }
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for member_name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=member_name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class TestDownloadAndExtract:

    def test_ssrf_rejected(self, tmp_path):
        from fastapi import HTTPException
        from app.plugin_installer import download_and_extract
        with pytest.raises(HTTPException) as exc_info:
            download_and_extract("my_plugin", "1.0.0", "http://127.0.0.1:1/archive.tar.gz", "tok", tmp_path)
        assert exc_info.value.status_code == 422

    def test_happy_path_extracts_and_renames(self, tmp_path, archive_server, monkeypatch):
        import app.plugin_installer as pi
        monkeypatch.setattr(pi, "assert_public_url", lambda *a, **k: None)
        _ArchiveHandler.archive_bytes = _build_tarball("my_plugin")
        host, port = archive_server.server_address
        url = f"http://{host}:{port}/my_plugin.tar.gz"

        final_path, manifest = pi.download_and_extract("my_plugin", "1.0.0", url, "test-token-123", tmp_path)

        assert final_path == tmp_path / "my_plugin-1.0.0"
        assert (final_path / "plugin.yaml").exists()
        assert (final_path / "router.py").exists()
        assert manifest["id"] == "my_plugin"
        assert _ArchiveHandler.received_auth_headers == ["Bearer test-token-123"]

        leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".plugin-")]
        assert leftovers == []

    def test_strips_wrapper_directory(self, tmp_path, archive_server, monkeypatch):
        import app.plugin_installer as pi
        monkeypatch.setattr(pi, "assert_public_url", lambda *a, **k: None)
        _ArchiveHandler.archive_bytes = _build_tarball("my_plugin", wrapped=True)
        host, port = archive_server.server_address
        url = f"http://{host}:{port}/my_plugin.tar.gz"

        final_path, manifest = pi.download_and_extract("my_plugin", "2.0.0", url, "tok", tmp_path)

        assert final_path == tmp_path / "my_plugin-2.0.0"
        assert (final_path / "plugin.yaml").exists()
        assert not (final_path / "repo-main").exists()
        assert manifest["id"] == "my_plugin"

    def test_id_mismatch_rejected_no_partial_dir(self, tmp_path, archive_server, monkeypatch):
        import app.plugin_installer as pi
        from fastapi import HTTPException
        monkeypatch.setattr(pi, "assert_public_url", lambda *a, **k: None)
        _ArchiveHandler.archive_bytes = _build_tarball("other_plugin")
        host, port = archive_server.server_address
        url = f"http://{host}:{port}/archive.tar.gz"

        with pytest.raises(HTTPException) as exc_info:
            pi.download_and_extract("my_plugin", "1.0.0", url, "tok", tmp_path)
        assert exc_info.value.status_code == 422

        assert not (tmp_path / "my_plugin-1.0.0").exists()
        leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".plugin-")]
        assert leftovers == []

    def test_download_size_cap(self, tmp_path, archive_server, monkeypatch):
        import app.plugin_installer as pi
        from fastapi import HTTPException
        monkeypatch.setattr(pi, "assert_public_url", lambda *a, **k: None)
        monkeypatch.setattr(pi, "MAX_DOWNLOAD_BYTES", 10)
        _ArchiveHandler.archive_bytes = _build_tarball("my_plugin")  # well over 10 bytes
        host, port = archive_server.server_address
        url = f"http://{host}:{port}/archive.tar.gz"

        with pytest.raises(HTTPException) as exc_info:
            pi.download_and_extract("my_plugin", "1.0.0", url, "tok", tmp_path)
        assert exc_info.value.status_code == 422
        assert "download limit" in exc_info.value.detail

        leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".plugin-")]
        assert leftovers == []

    def test_update_replaces_existing_versioned_dir(self, tmp_path, archive_server, monkeypatch):
        """Re-installing the same plugin_id+version overwrites the prior extraction."""
        import app.plugin_installer as pi
        monkeypatch.setattr(pi, "assert_public_url", lambda *a, **k: None)
        host, port = archive_server.server_address
        url = f"http://{host}:{port}/archive.tar.gz"

        _ArchiveHandler.archive_bytes = _build_tarball("my_plugin")
        first_path, _ = pi.download_and_extract("my_plugin", "1.0.0", url, "tok", tmp_path)
        (first_path / "marker.txt").write_text("v1")

        _ArchiveHandler.archive_bytes = _build_tarball("my_plugin")
        second_path, _ = pi.download_and_extract("my_plugin", "1.0.0", url, "tok", tmp_path)

        assert second_path == first_path
        assert not (second_path / "marker.txt").exists()


# ---------------------------------------------------------------------------
# _gc_orphaned_local_installs
# ---------------------------------------------------------------------------

class TestGcOrphanedLocalInstalls:

    def test_missing_root_is_noop(self, tmp_path):
        pytest.importorskip("sqlmodel")
        from app.plugin_installer import _gc_orphaned_local_installs

        class FakeSession:
            def exec(self, stmt):
                raise AssertionError("should not query when root doesn't exist")

        _gc_orphaned_local_installs(FakeSession(), tmp_path / "does-not-exist")

    def test_removes_unreferenced_dirs(self, tmp_path):
        pytest.importorskip("sqlmodel")
        from app.plugin_installer import _gc_orphaned_local_installs

        root = tmp_path / "dynamic_plugins"
        root.mkdir()
        active_dir = root / "plugin_a-1.0.0"
        active_dir.mkdir()
        orphan_dir = root / "plugin_b-0.9.0"
        orphan_dir.mkdir()
        hidden_dir = root / ".tmp-extract-leftover"
        hidden_dir.mkdir()
        stray_file = root / "enabled_overrides.json"
        stray_file.write_text("[]")

        class FakeQueryResult:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        class FakeSession:
            def exec(self, stmt):
                return FakeQueryResult([SimpleNamespace(install_path=str(active_dir))])

        _gc_orphaned_local_installs(FakeSession(), root)

        assert active_dir.exists()
        assert not orphan_dir.exists()
        assert hidden_dir.exists()   # dotfiles/dirs skipped
        assert stray_file.exists()   # non-directories skipped
