from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_web import _BROWSER_FUNCTIONALITY_PATCH
from natureai_next.server.library_media_state_provider_web import (
    _LIBRARY_MEDIA_STATE_PROVIDER_PATCH,
    _NAVIGATION_MEDIA_FILTER_TABS,
    _NAVIGATION_NON_LIBRARY_TABS,
    patch_library_media_state_provider_response,
)
from natureai_next.server.media_detail_web import _MEDIA_DETAIL_PATCH
from natureai_next.server.modular_shell_composition import foundation_composition_registry
from natureai_next.server.web_module_contracts import FOUNDATION_WEB_MODULES


def test_library_media_state_provider_owns_immutable_items_and_filter() -> None:
    script = _LIBRARY_MEDIA_STATE_PROVIDER_PATCH.decode("utf-8")

    for token in (
        'let items=Object.freeze([]),filter="all",cursor=""',
        "const freezeItems=value=>Object.freeze(",
        'const snapshot=()=>Object.freeze({module_id:"library.catalog",items,filter})',
        'new CustomEvent("fieldora:library-media-state-changed"',
        "replaceItems(result?.items||[],reset)",
        'kind=filter==="all"?"":filter',
        "loadMedia=async function(reset=true){return load(reset);}",
        "button.onclick=()=>selectFilter(button.dataset.mediaFilter)",
        'button.setAttribute("aria-selected",String(active))',
        'button.setAttribute("role","tab")',
        'catch(error){cards("media-grid",[],x=>x,error.message);return snapshot()}',
    ):
        assert token in script

    assert "media=reset?" not in script
    assert "mediaFilter=" not in script


def test_library_gallery_and_detail_consume_frozen_state_event() -> None:
    gallery = _BROWSER_FUNCTIONALITY_PATCH.decode("utf-8")
    detail = _MEDIA_DETAIL_PATCH.decode("utf-8")

    for script in (gallery, detail):
        assert "fieldora:library-media-state-changed" in script
        assert "libraryMediaSnapshot" in script

    assert "libraryMediaSnapshot.items" in gallery
    assert "libraryMediaSnapshot.filter" in gallery
    assert "let shown=media.filter" not in gallery
    assert "const m=media.find" not in gallery

    assert "libraryMediaSnapshot.items" in detail
    assert 'typeof media!=="undefined"' not in detail


def test_library_media_owner_retires_only_generic_media_filter_tabs() -> None:
    response = ApiResponse(
        200,
        b"/* navigation */" + _NAVIGATION_MEDIA_FILTER_TABS + b"/* tail */",
        "text/javascript; charset=utf-8",
    )

    patched = patch_library_media_state_provider_response("/app.js", response)

    assert _NAVIGATION_MEDIA_FILTER_TABS not in patched.body
    assert _NAVIGATION_NON_LIBRARY_TABS in patched.body
    assert b'"observation-filter"' in patched.body
    assert b'"research-domain"' in patched.body
    assert _LIBRARY_MEDIA_STATE_PROVIDER_PATCH in patched.body


def test_library_media_state_provider_is_omitted_with_library_module() -> None:
    route_ids = tuple(spec.module_id for spec in FOUNDATION_WEB_MODULES)
    no_library = foundation_composition_registry(
        module_id for module_id in route_ids if module_id != "library.catalog"
    )
    response = ApiResponse(
        200,
        b"/* managed shell */" + _NAVIGATION_MEDIA_FILTER_TABS,
        "text/javascript; charset=utf-8",
    )

    suppressed = patch_library_media_state_provider_response(
        "/app.js", response, registry=no_library
    )
    defaulted = patch_library_media_state_provider_response("/app.js", response)

    assert _NAVIGATION_MEDIA_FILTER_TABS not in suppressed.body
    assert _NAVIGATION_NON_LIBRARY_TABS in suppressed.body
    assert _LIBRARY_MEDIA_STATE_PROVIDER_PATCH not in suppressed.body
    assert _NAVIGATION_MEDIA_FILTER_TABS not in defaulted.body
    assert _NAVIGATION_NON_LIBRARY_TABS in defaulted.body
    assert _LIBRARY_MEDIA_STATE_PROVIDER_PATCH in defaulted.body
