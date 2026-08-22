node_keys = { "place" }
way_keys = { "highway", "building", "natural", "water", "landuse", "leisure" }

function node_function()
  local place = Find("place")
  if place ~= "" then
    Layer("place")
    Attribute("class", place)
    Attribute("name", Find("name"))
    if place == "city" then MinZoom(3) elseif place == "town" then MinZoom(6) else MinZoom(10) end
  end
end

function way_function()
  local highway = Find("highway")
  if highway ~= "" then
    Layer("transportation", false)
    if highway == "residential" or highway == "unclassified" then highway = "minor" end
    Attribute("class", highway)
    Attribute("name", Find("name"))
  end
  if Find("building") ~= "" then Layer("building", true) end
  if Find("natural") == "water" or Find("water") ~= "" then Layer("water", true) end
  local landuse = Find("landuse")
  if landuse == "" then landuse = Find("leisure") end
  if landuse ~= "" then Layer("landuse", true); Attribute("class", landuse) end
end
