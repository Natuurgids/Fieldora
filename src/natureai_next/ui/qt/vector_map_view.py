"""Lazy WebEngine view shell for independent local vector MBTiles databases."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from natureai_next.ui.qt.map_archive_scheme import package_authority, package_id_from_scheme_url
from natureai_next.ui.qt.vector_style import load_aperture_street_style


def vector_overlay_data(
    result: Any, temporal_frame: Any = None, gps_track: Any = None
) -> dict[str, object]:
    """Convert map projections into local GeoJSON overlay collections."""
    observations = result.observations if temporal_frame is None else temporal_frame.observations

    def point(longitude: float, latitude: float, **properties: object) -> dict[str, object]:
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
            "properties": properties,
        }

    observation_features = [
        point(
            item.longitude,
            item.latitude,
            kind="observation",
            public_id=item.observation_public_id,
            label=item.scientific_name or "Observation",
        )
        for item in observations
    ]
    clusters = getattr(result, "asset_clusters", None)
    if clusters is None:
        asset_features = [
            point(
                item.longitude, item.latitude, kind="photo", public_id=item.asset_public_id,
                role=item.location_role,
                label=("Subject location" if item.location_role == "subject" else "Capture location"),
            )
            for item in result.assets
        ]
    else:
        asset_features = [
            point(
                item.longitude, item.latitude, kind="media-cluster", count=item.total_count,
                image_count=item.image_count, video_count=item.video_count, audio_count=item.audio_count,
                capture_count=item.capture_count, subject_count=item.subject_count,
                user_defined_count=item.user_defined_count, level=item.level, label=item.label,
            )
            for item in clusters
        ]
    site_features = [
        point(item.longitude, item.latitude, kind="site", public_id=item.public_id, label=item.name)
        for item in result.sites
        if item.latitude is not None and item.longitude is not None
    ]
    track_features: list[dict[str, object]] = []
    if temporal_frame is not None and temporal_frame.track is not None:
        coordinates = [[item.longitude, item.latitude] for item in temporal_frame.track.points]
        if len(coordinates) >= 2:
            track_features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coordinates},
                    "properties": {"kind": "track"},
                }
            )
    if gps_track is not None:
        for segment in gps_track.segments:
            coordinates = [[item.longitude, item.latitude] for item in segment]
            if len(coordinates) >= 2:
                track_features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": coordinates},
                        "properties": {"kind": "gpx", "name": gps_track.name},
                    }
                )

    def collection(features: list[dict[str, object]]) -> dict[str, object]:
        return {"type": "FeatureCollection", "features": features}

    return {
        "aperture-observations": collection(observation_features),
        "aperture-assets": collection(asset_features),
        "aperture-sites": collection(site_features),
        "aperture-track": collection(track_features),
    }


def vector_map_html(
    package_public_id: str,
    asset_root: Path,
    *,
    longitude: float = 0.0,
    latitude: float = 0.0,
    zoom: int = 2,
    base_url: str | None = None,
    nautical_overlay_count: int = 0,
) -> str:
    """Build a local MapLibre document backed by direct MBTiles tile requests."""
    authority = package_authority(package_public_id)
    package_id_from_scheme_url("aperture-map", authority, "/tile/0/0/0.pbf")
    if base_url:
        css = base_url + "/assets/maplibre-gl.css"
        maplibre = base_url + "/assets/maplibre-gl.js"
        tile_url = base_url + "/tile/{z}/{x}/{y}.pbf"
    else:
        css = (asset_root / "maplibre-gl.css").resolve().as_uri()
        maplibre = (asset_root / "maplibre-gl.js").resolve().as_uri()
        tile_url = f"aperture-map://{authority}/tile/{{z}}/{{x}}/{{y}}.pbf"
    style = load_aperture_street_style(asset_root / "aperture-streets-v1.json", tile_url)
    for index in range(nautical_overlay_count):
        source_id = f"openseamap-{index}"
        style["sources"][source_id] = {
            "type": "raster",
            "tiles": [f"{base_url}/nautical/{index}/{{z}}/{{x}}/{{y}}.png"],
            "tileSize": 256,
        }
        style["layers"].append(
            {
                "id": f"openseamap-seamarks-{index}",
                "type": "raster",
                "source": source_id,
                "paint": {"raster-opacity": 1.0, "raster-fade-duration": 0},
            }
        )
    config = json.dumps({"style": style, "center": [longitude, latitude], "zoom": zoom})
    return f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><meta name=\"referrer\" content=\"no-referrer\">
<link rel=\"stylesheet\" href=\"{html.escape(css, quote=True)}\">
<style>html,body,#map{{width:100%;height:100%;margin:0}}#status,#coordinates,#legend{{position:absolute;z-index:2;padding:8px;background:#fffffff0;font:12px sans-serif}}#coordinates{{right:8px;bottom:24px}}#legend{{left:8px;bottom:24px;line-height:1.6}}.key{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}}.aperture-map-label{{font:600 12px/1.2 sans-serif;color:#273038;text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff;white-space:nowrap;pointer-events:none}}.aperture-road-label{{font-size:11px;font-weight:500;color:#4b4034}}</style>
</head><body><div id=\"status\">Preparing offline vector map…</div><div id=\"coordinates\">Coordinates unavailable</div><div id=\"legend\"><span class=\"key\" style=\"background:#be3a34\"></span>Observation&nbsp; <span class=\"key\" style=\"background:#2f8f5b\"></span>Photo&nbsp; <span class=\"key\" style=\"background:#285c9d\"></span>Site&nbsp; <span class=\"key\" style=\"background:#e07b24\"></span>GPS track</div><div id=\"map\"></div>
<script src=\"{html.escape(maplibre, quote=True)}\"></script>
<script>const aperture={config};
try {{
const map=new maplibregl.Map({{container:'map',style:aperture.style,center:aperture.center,zoom:aperture.zoom,maxZoom:18}});
window.apertureMap={{map:map}}; window.apertureOverlayData={{}}; window.apertureOverlayRevision=0;
window.apertureLabelMarkers=[];
window.apertureRefreshLabels=()=>{{
 for(const marker of window.apertureLabelMarkers)marker.remove();
 window.apertureLabelMarkers=[];
 const seen=new Set();
 const add=(name,coordinates,road=false)=>{{
  if(!name||!Array.isArray(coordinates)||coordinates.length<2)return;
  const key=(road?'road:':'place:')+name;
  if(seen.has(key)||window.apertureLabelMarkers.length>=150)return;
  seen.add(key);
  const element=document.createElement('div');
  element.className='aperture-map-label'+(road?' aperture-road-label':'');
  element.textContent=String(name);
  window.apertureLabelMarkers.push(new maplibregl.Marker({{element,anchor:'center'}}).setLngLat(coordinates).addTo(map));
 }};
 try{{
  for(const feature of map.querySourceFeatures('aperture',{{sourceLayer:'place'}})){{
   if(feature.geometry&&feature.geometry.type==='Point')add(feature.properties&&feature.properties.name,feature.geometry.coordinates,false);
  }}
  for(const sourceLayer of ['transportation_name','transportation']){{
   for(const feature of map.querySourceFeatures('aperture',{{sourceLayer}})){{
    const geometry=feature.geometry;
    const lines=geometry&&geometry.type==='MultiLineString'?geometry.coordinates:[geometry&&geometry.coordinates];
    for(const line of lines){{if(Array.isArray(line)&&line.length)add(feature.properties&&feature.properties.name,line[Math.floor(line.length/2)],true);}}
   }}
  }}
 }}catch(error){{console.error('Offline label refresh failed',error);}}
}};
map.addControl(new maplibregl.NavigationControl({{showCompass:true,showZoom:true}}),'top-right');
map.on('error',event=>{{const message=(event&&event.error&&event.error.message)||'Unknown vector tile error';const status=document.getElementById('status');if(status){{status.style.display='block';status.textContent='Offline basemap error: '+message;}}console.error(event&&event.error?event.error:event);}});
const overlaySources=['aperture-observations','aperture-assets','aperture-sites','aperture-track'];
const overlayLayers=[
{{id:'aperture-track-line',type:'line',source:'aperture-track',paint:{{'line-color':['case',['==',['get','kind'],'gpx'],'#e07b24','#6f3fb6'],'line-width':4}}}},
{{id:'aperture-site-points',type:'circle',source:'aperture-sites',paint:{{'circle-radius':6,'circle-color':'#285c9d','circle-stroke-color':'#fff','circle-stroke-width':2}}}},
{{id:'aperture-observation-points',type:'circle',source:'aperture-observations',paint:{{'circle-radius':7,'circle-color':'#be3a34','circle-stroke-color':'#fff','circle-stroke-width':2}}}},
{{id:'aperture-media-clusters',type:'circle',source:'aperture-assets',paint:{{'circle-radius':['interpolate',['linear'],['get','count'],1,10,100,14,1000,18],'circle-color':'#2f8f5b','circle-stroke-color':'#fff','circle-stroke-width':2}}}},
{{id:'aperture-media-counts',type:'symbol',source:'aperture-assets',layout:{{'text-field':['case',['>', ['get','count'],999],'999+',['to-string',['get','count']]],'text-size':11,'text-allow-overlap':true,'text-ignore-placement':true}},paint:{{'text-color':'#ffffff'}}}}
];
window.apertureEnsureOverlays=()=>{{
 if(!map.isStyleLoaded())return false;
 try {{
  const empty={{type:'FeatureCollection',features:[]}};
  for(const name of overlaySources){{
   if(!map.getSource(name))map.addSource(name,{{type:'geojson',data:window.apertureOverlayData[name]||empty}});
  }}
  for(const layer of overlayLayers){{
   if(!map.getLayer(layer.id))map.addLayer(layer);
   if(map.getLayer(layer.id))map.setLayoutProperty(layer.id,'visibility','visible');
  }}
  // Offline styles may finish appending layers after the initial load event. Always
  // restore the complete Aperture overlay stack to the foreground, then replay the
  // latest GeoJSON. The operation is idempotent and safe after style/package reloads.
  const overlayIds=overlayLayers.map(layer=>layer.id);
  for(const id of overlayIds){{if(map.getLayer(id))map.moveLayer(id);}}
  for(const name of overlaySources){{
   const source=map.getSource(name);
   if(source&&source.setData)source.setData(window.apertureOverlayData[name]||empty);
  }}
  window.apertureOverlayDiagnostics={{
   revision:window.apertureOverlayRevision,
   features:Object.fromEntries(overlaySources.map(name=>[name,((window.apertureOverlayData[name]||empty).features||[]).length])),
   layers:overlayIds.filter(id=>!!map.getLayer(id))
  }};
  return true;
 }} catch(error) {{console.error('Aperture overlay restore failed',error);return false;}}
}};
window.apertureScheduleOverlayRestore=()=>{{
 window.apertureEnsureOverlays();
 requestAnimationFrame(()=>window.apertureEnsureOverlays());
 setTimeout(()=>window.apertureEnsureOverlays(),50);
 setTimeout(()=>window.apertureEnsureOverlays(),250);
}};
map.once('load',()=>{{
 window.apertureScheduleOverlayRestore();
 window.apertureRefreshLabels();
 const status=document.getElementById('status');if(status){{status.textContent='Offline basemap loaded';setTimeout(()=>{{status.style.display='none';}},1500);}}
}});
map.on('style.load',()=>{{window.apertureScheduleOverlayRestore();if(window.apertureEnsureProjectDrawing)window.apertureEnsureProjectDrawing();}});
map.on('styledata',()=>{{window.apertureScheduleOverlayRestore();}});
map.on('idle',()=>{{window.apertureEnsureOverlays();}});
const coordinates=document.getElementById('coordinates');
map.on('mousemove',event=>coordinates.textContent=event.lngLat.lat.toFixed(5)+', '+event.lngLat.lng.toFixed(5)+' • zoom '+map.getZoom().toFixed(1));
window.apertureProjectDrawing={{active:false,points:[]}};
window.apertureEnsureProjectDrawing=()=>{{
 if(!map.isStyleLoaded())return false;
 const data={{type:'FeatureCollection',features:[]}};
 const points=window.apertureProjectDrawing.points;
 if(points.length) data.features.push({{type:'Feature',properties:{{kind:'vertices'}},geometry:{{type:'LineString',coordinates:points}}}});
 if(points.length>=3) data.features.push({{type:'Feature',properties:{{kind:'area'}},geometry:{{type:'Polygon',coordinates:[[...points,points[0]]]}}}});
 if(!map.getSource('aperture-project-drawing')) map.addSource('aperture-project-drawing',{{type:'geojson',data:data}}); else map.getSource('aperture-project-drawing').setData(data);
 if(!map.getLayer('aperture-project-fill')) map.addLayer({{id:'aperture-project-fill',type:'fill',source:'aperture-project-drawing',filter:['==',['geometry-type'],'Polygon'],paint:{{'fill-color':'#2f9e62','fill-opacity':0.25}}}});
 if(!map.getLayer('aperture-project-line')) map.addLayer({{id:'aperture-project-line',type:'line',source:'aperture-project-drawing',paint:{{'line-color':'#0b6b3a','line-width':4}}}});
 return true;
}};
window.apertureStartProjectDrawing=()=>{{window.apertureProjectDrawing={{active:true,points:[]}};map.getCanvas().style.cursor='crosshair';window.apertureEnsureProjectDrawing();}};
window.apertureUndoProjectPoint=()=>{{window.apertureProjectDrawing.points.pop();window.apertureEnsureProjectDrawing();}};
window.apertureClearProjectDrawing=()=>{{window.apertureProjectDrawing={{active:false,points:[]}};map.getCanvas().style.cursor='';window.apertureEnsureProjectDrawing();}};
window.apertureSetProjectArea=(feature)=>{{
 const geometry=feature&&feature.type==='Feature'?feature.geometry:feature;
 const rings=geometry&&geometry.type==='Polygon'?geometry.coordinates:null;
 const ring=Array.isArray(rings)&&Array.isArray(rings[0])?rings[0]:[];
 const points=ring.map(point=>[Number(point[0]),Number(point[1])]).filter(point=>Number.isFinite(point[0])&&Number.isFinite(point[1]));
 if(points.length>1&&points[0][0]===points[points.length-1][0]&&points[0][1]===points[points.length-1][1])points.pop();
 window.apertureProjectDrawing={{active:false,points:points}};
 window.apertureEnsureProjectDrawing();
 if(points.length>=3){{
  const bounds=new maplibregl.LngLatBounds(points[0],points[0]);
  for(const point of points)bounds.extend(point);
  window.apertureSuppressMove=true;
  map.fitBounds(bounds,{{padding:60,maxZoom:15,duration:0}});
 }}
 return points.length;
}};
window.apertureFinishProjectDrawing=()=>{{const p=window.apertureProjectDrawing.points;if(p.length<3){{document.title='aperture-project-error:Select at least three points.';return;}}window.apertureProjectDrawing.active=false;map.getCanvas().style.cursor='';document.title='aperture-project-polygon:'+JSON.stringify({{type:'Feature',properties:{{}},geometry:{{type:'Polygon',coordinates:[[...p,p[0]]]}}}});}};
map.on('click',event=>{{if(!window.apertureProjectDrawing.active)return;window.apertureProjectDrawing.points.push([event.lngLat.lng,event.lngLat.lat]);window.apertureEnsureProjectDrawing();}});
map.on('moveend',()=>{{window.apertureRefreshLabels();const center=map.getCenter();coordinates.textContent=center.lat.toFixed(5)+', '+center.lng.toFixed(5)+' • zoom '+map.getZoom().toFixed(1);if(window.apertureSuppressMove){{window.apertureSuppressMove=false;}}else{{document.title='aperture-view:'+JSON.stringify({{latitude:center.lat,longitude:center.lng,zoom:map.getZoom()}});}}}});
}} catch(error) {{ const status=document.getElementById('status');if(status)status.textContent='MBTiles renderer v2 unavailable: '+error.message;console.error(error); }}
</script></body></html>"""


def create_vector_map_view(profile: Any, package: Any, parent: Any = None) -> Any:
    """Create a page on the explicit map-only profile; import WebEngine lazily."""
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView

    packages = tuple(package) if isinstance(package, tuple | list) else (package,)
    from natureai_next.domain.maps import is_nautical_overlay

    vector_packages = tuple(item for item in packages if not is_nautical_overlay(item))
    nautical_overlays = tuple(item for item in packages if is_nautical_overlay(item))
    primary = vector_packages[0]
    asset_root = Path(__file__).resolve().parents[2] / "resources" / "map_renderer"
    page = QWebEnginePage(profile, parent)
    view = QWebEngineView(parent)
    view.setPage(page)
    from natureai_next.application.map_workspace import package_viewpoint, packages_viewpoint
    from natureai_next.ui.qt.vector_map_server import VectorMapLoopbackServer

    viewpoint = (
        packages_viewpoint(vector_packages)
        if len(vector_packages) > 1
        else package_viewpoint(primary)
    )

    def document_factory(base_url: str) -> str:
        return vector_map_html(
            primary.public_id,
            asset_root,
            longitude=viewpoint.longitude,
            latitude=viewpoint.latitude,
            zoom=viewpoint.zoom,
            base_url=base_url,
            nautical_overlay_count=len(nautical_overlays),
        )

    server = VectorMapLoopbackServer(packages, asset_root, document_factory)
    view.aperture_map_server = server
    view.destroyed.connect(lambda *_: server.close())
    from PySide6.QtCore import QUrl

    view.setUrl(QUrl(server.document_url))
    viewpoint_callbacks: list[Any] = []
    project_polygon_callbacks: list[Any] = []
    project_error_callbacks: list[Any] = []

    def title_changed(title: str) -> None:
        if title.startswith("aperture-project-polygon:"):
            try:
                feature = json.loads(title.removeprefix("aperture-project-polygon:"))
            except json.JSONDecodeError:
                return
            for callback in tuple(project_polygon_callbacks):
                callback(feature)
            return
        if title.startswith("aperture-project-error:"):
            for callback in tuple(project_error_callbacks):
                callback(title.removeprefix("aperture-project-error:"))
            return
        if not title.startswith("aperture-view:"):
            return
        try:
            payload = json.loads(title.removeprefix("aperture-view:"))
            latitude = float(payload["latitude"])
            longitude = float(payload["longitude"])
            zoom = float(payload["zoom"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return
        for callback in tuple(viewpoint_callbacks):
            callback(latitude, longitude, zoom)

    page.titleChanged.connect(title_changed)

    def set_viewpoint(longitude: float, latitude: float, zoom: int) -> None:
        options = json.dumps({"center": [longitude, latitude], "zoom": zoom})
        page.runJavaScript(
            f"if(window.apertureMap){{window.apertureSuppressMove=true;window.apertureMap.map.jumpTo({options});}}"
        )

    def connect_viewpoint(callback: Any) -> None:
        viewpoint_callbacks.append(callback)

    def connect_project_polygon(callback: Any) -> None:
        project_polygon_callbacks.append(callback)

    def connect_project_error(callback: Any) -> None:
        project_error_callbacks.append(callback)

    latest_overlay_payload = json.dumps(
        {
            name: {"type": "FeatureCollection", "features": []}
            for name in (
                "aperture-observations",
                "aperture-assets",
                "aperture-sites",
                "aperture-track",
            )
        }
    )
    latest_project_area_payload = "null"

    def apply_latest_overlays() -> None:
        page.runJavaScript(
            "window.apertureOverlayData="
            + latest_overlay_payload
            + ";window.apertureOverlayRevision=(window.apertureOverlayRevision||0)+1;"
            + "if(window.apertureScheduleOverlayRestore){window.apertureScheduleOverlayRestore();}"
            + "else if(window.apertureEnsureOverlays){window.apertureEnsureOverlays();}"
        )

    def page_loaded(ok: bool) -> None:
        if not ok:
            return
        # The first overlay update often arrives while QWebEngineView is still on
        # about:blank. Replay retained data after navigation and after MapLibre has
        # had an opportunity to complete its asynchronous style load.
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, apply_latest_overlays)
        QTimer.singleShot(100, apply_latest_overlays)
        QTimer.singleShot(500, apply_latest_overlays)

        def replay_project_area() -> None:
            if latest_project_area_payload != "null":
                page.runJavaScript(
                    "if(window.apertureSetProjectArea)window.apertureSetProjectArea("
                    + latest_project_area_payload
                    + ");"
                )

        QTimer.singleShot(0, replay_project_area)
        QTimer.singleShot(150, replay_project_area)
        QTimer.singleShot(600, replay_project_area)

    view.loadFinished.connect(page_loaded)

    def set_overlays(result: Any, temporal_frame: Any = None, gps_track: Any = None) -> None:
        nonlocal latest_overlay_payload
        latest_overlay_payload = json.dumps(vector_overlay_data(result, temporal_frame, gps_track))
        apply_latest_overlays()

    def set_project_area(feature: dict[str, object] | None) -> None:
        nonlocal latest_project_area_payload
        latest_project_area_payload = json.dumps(feature) if feature else "null"
        if feature:
            page.runJavaScript(
                "if(window.apertureSetProjectArea)window.apertureSetProjectArea("
                + latest_project_area_payload
                + ");"
            )

    view.aperture_set_viewpoint = set_viewpoint
    view.aperture_connect_viewpoint = connect_viewpoint
    view.aperture_connect_project_polygon = connect_project_polygon
    view.aperture_connect_project_error = connect_project_error
    view.aperture_set_overlays = set_overlays
    view.aperture_set_project_area = set_project_area
    return view
