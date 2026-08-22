from natureai_next.application.map_workspace import viewport_bounds


def test_default_viewport_bounds_cover_full_five_by_five_canvas():
    center_latitude = 50.8503
    center_longitude = 4.3517
    zoom = 10

    bounds = viewport_bounds(center_latitude, center_longitude, zoom)
    expected = viewport_bounds(center_latitude, center_longitude, zoom, tile_radius=2)

    assert bounds == expected


def test_visible_edge_coordinates_remain_inside_spatial_query():
    latitude = 50.8503
    longitude = 4.3517
    zoom = 10
    bounds = viewport_bounds(latitude, longitude, zoom)

    assert bounds.min_latitude < latitude < bounds.max_latitude
    assert bounds.min_longitude < longitude < bounds.max_longitude
    assert bounds.max_latitude - bounds.min_latitude > 0
    assert bounds.max_longitude - bounds.min_longitude > 0
