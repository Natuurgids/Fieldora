from __future__ import annotations

import contextlib
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.bounded_upload_web import (
    BoundedUploadWebApiMixin,
    patch_bounded_upload_response,
)
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi


_FULL_BUFFER_SCRIPT = b'''async function upload(file){
 const bytes=await file.arrayBuffer(),hash=[...new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))].map(x=>x.toString(16).padStart(2,"0")).join("");
 for(let start=0;start<file.size;start+=4*1024*1024){const end=Math.min(file.size,start+4*1024*1024);await api("/upload",{body:bytes.slice(start,end)})}
 return hash;
}
 async function digestFile(file){
  const bytes=await file.arrayBuffer();
  const digest=await crypto.subtle.digest("SHA-256",bytes);
  return {bytes,hash:[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,"0")).join("")};
 }
'''


class _BaseApi:
    def dispatch(self, method, target, headers, body):
        return ApiResponse(200, _FULL_BUFFER_SCRIPT, "text/javascript")


class _PatchedApi(BoundedUploadWebApiMixin, _BaseApi):
    pass


def test_web052_composition_is_outermost_and_removes_whole_file_upload_buffers() -> None:
    assert OfflineFirstFieldoraApi.__mro__[1] is BoundedUploadWebApiMixin
    response = patch_bounded_upload_response(
        "/app.js", ApiResponse(200, _FULL_BUFFER_SCRIPT, "text/javascript")
    )
    script = response.body.decode("utf-8")

    assert "file.arrayBuffer()" not in script
    assert "window.fieldoraBoundedSha256(file)" in script
    assert "body:file.slice(start,end)" in script
    assert "chunkSize=4*1024*1024" in script
    assert "crypto.subtle.digest" not in script


@contextlib.contextmanager
def _web_fixture(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><script src="/app.js"></script></body></html>',
        encoding="utf-8",
    )
    response = _PatchedApi().dispatch("GET", "/app.js", {}, b"")
    (tmp_path / "app.js").write_bytes(response.body)

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            pass

    def handler(*args: object, **kwargs: object):
        return Handler(*args, directory=str(tmp_path), **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_web052_incremental_sha256_matches_known_digest_and_bounds_each_read(
    tmp_path: Path,
    browser_name: str,
) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        result = page.evaluate(
            """async () => {
              const original=Blob.prototype.arrayBuffer;
              let maxRead=0,reads=0;
              Blob.prototype.arrayBuffer=async function(){maxRead=Math.max(maxRead,this.size);reads+=1;return original.call(this)};
              try{
                const small=new Blob([new TextEncoder().encode('abc')]);
                const smallHash=await window.fieldoraBoundedSha256(small,2);
                const big=new Blob([new Uint8Array(9*1024*1024+17)]);
                await window.fieldoraBoundedSha256(big);
                return {smallHash,maxRead,reads,bigSize:big.size};
              } finally {Blob.prototype.arrayBuffer=original;}
            }"""
        )
        assert result["smallHash"] == (
            "ba7816bf8f01cfea414140de5dae2223"
            "b00361a396177a9cb410ff61f20015ad"
        )
        assert result["maxRead"] <= 4 * 1024 * 1024
        assert result["maxRead"] < result["bigSize"]
        assert result["reads"] >= 5
        browser.close()
