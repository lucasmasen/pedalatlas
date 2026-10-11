"""Settlement centroids and schematic highway connections.

Coordinates are public town and junction centroids for orientation.
Straight segments are not a surveyed bicycle route, and a mapped road is
not evidence that cycling is safe, legal, or currently possible.
"""

from __future__ import annotations

REGIONS = [
    ("alaska", "Alaska", "United States", "Eastern and southcentral Alaska anchors used by northbound and southbound touring chats."),
    ("yukon", "Yukon", "Canada", "Alaska Highway communities from Beaver Creek through Watson Lake."),
    ("northern-bc", "Northern British Columbia", "Canada", "Cassiar Highway and Highway 16 communities north of Prince George."),
    ("southern-bc", "Southern British Columbia", "Canada", "Highway 97 and Highway 1 corridor from the Cariboo toward Vancouver."),
]

# id, name, kind, region, lat, lon, scope, featured, ambiguous, border, aliases, summary
LOCATIONS = [
    ("anchorage", "Anchorage", "town", "alaska", 61.2181, -149.9003, "corridor", True, False, False, ["Anchorage"], "Largest city in Alaska and a common start or resupply point on the road system."),
    ("palmer", "Palmer", "town", "alaska", 61.5994, -149.1128, "corridor", False, False, False, ["Palmer"], "Matanuska Valley town on the Glenn Highway east of Anchorage."),
    ("wasilla", "Wasilla", "town", "alaska", 61.5814, -149.4394, "corridor", False, False, False, ["Wasilla"], "Town north of Anchorage on the Parks Highway."),
    ("glennallen", "Glennallen", "town", "alaska", 62.1092, -145.5464, "corridor", False, False, False, ["Glennallen"], "Junction community where the Glenn Highway meets the Richardson Highway."),
    ("fairbanks", "Fairbanks", "town", "alaska", 64.8378, -147.7164, "corridor", True, False, False, ["Fairbanks"], "Interior Alaska city on the Parks and Richardson Highways."),
    ("denali", "Denali", "park", "alaska", 63.730, -148.914, "corridor", False, False, False, ["Denali", "Denali Park"], "Park entrance area along the Parks Highway between Fairbanks and Wasilla."),
    ("delta-junction", "Delta Junction", "town", "alaska", 64.0375, -145.7322, "corridor", False, False, False, ["Delta Junction"], "Official end of the Alaska Highway, southeast of Fairbanks."),
    ("tok", "Tok", "town", "alaska", 63.3367, -142.9856, "corridor", True, False, False, ["Tok"], "Interior junction of the Alaska Highway and the Tok Cut-Off."),
    ("chicken", "Chicken", "town", "alaska", 64.073, -141.934, "corridor", False, True, False, ["Chicken"], "Small Taylor Highway settlement near the Yukon border."),
    ("northway", "Northway", "town", "alaska", 62.9617, -141.9372, "corridor", False, False, False, ["Northway"], "Alaska Highway community west of the Canada border."),
    ("port-alcan", "Port Alcan", "border", "alaska", 62.616, -141.001, "corridor", False, False, True, ["Port Alcan", "Alcan border"], "Alaska Highway land border between Alaska and Yukon."),
    ("seward", "Seward", "town", "alaska", 60.1042, -149.4422, "adjacent", False, False, False, ["Seward"], "Kenai Peninsula port south of Anchorage, off the main interior highway spine."),
    ("homer", "Homer", "town", "alaska", 59.6425, -151.5483, "adjacent", False, False, False, ["Homer"], "Kenai Peninsula town southwest of Anchorage."),
    ("valdez", "Valdez", "town", "alaska", 61.1308, -146.3483, "adjacent", False, False, False, ["Valdez"], "Prince William Sound port at the south end of the Richardson Highway."),
    ("haines", "Haines", "town", "alaska", 59.235, -135.445, "corridor", False, False, True, ["Haines"], "Lynn Canal town at the south end of the Haines Highway."),
    ("skagway", "Skagway", "town", "alaska", 59.4583, -135.3139, "corridor", False, False, True, ["Skagway"], "Lynn Canal town connected to Whitehorse by the Klondike Highway."),
    ("juneau", "Juneau", "town", "alaska", 58.3019, -134.4197, "adjacent", False, False, False, ["Juneau"], "Alaska capital. It is not connected to the interior highway network by road."),
    ("beaver-creek", "Beaver Creek", "town", "yukon", 62.383, -140.878, "corridor", True, False, True, ["Beaver Creek"], "First Yukon community east of the Alaska Highway border."),
    ("destruction-bay", "Destruction Bay", "town", "yukon", 61.2528, -138.8022, "corridor", False, False, False, ["Destruction Bay"], "Kluane-area stop on the Alaska Highway."),
    ("haines-junction", "Haines Junction", "town", "yukon", 60.7522, -137.5106, "corridor", False, False, False, ["Haines Junction"], "Junction of the Alaska Highway and the Haines Highway."),
    ("whitehorse", "Whitehorse", "town", "yukon", 60.7212, -135.0568, "corridor", True, False, False, ["Whitehorse"], "Capital of Yukon, on the Alaska Highway."),
    ("carcross", "Carcross", "town", "yukon", 60.1678, -134.7061, "corridor", False, False, False, ["Carcross"], "Community south of Whitehorse on the way toward Skagway."),
    ("teslin", "Teslin", "town", "yukon", 60.1672, -132.7217, "corridor", False, False, False, ["Teslin"], "Alaska Highway community between Whitehorse and Watson Lake."),
    ("watson-lake", "Watson Lake", "town", "yukon", 60.0631, -128.7089, "corridor", True, False, False, ["Watson Lake"], "Alaska Highway community at the north end of the Cassiar Highway."),
    ("dease-lake", "Dease Lake", "town", "northern-bc", 58.437, -130.013, "corridor", False, False, False, ["Dease Lake"], "Cassiar Highway community in northern British Columbia."),
    ("iskut", "Iskut", "town", "northern-bc", 57.846, -129.990, "corridor", False, False, False, ["Iskut"], "Community on the Cassiar Highway south of Dease Lake."),
    ("meziadin", "Meziadin Junction", "junction", "northern-bc", 56.098, -129.318, "corridor", False, False, False, ["Meziadin Junction", "Meziadin"], "Cassiar Highway junction for the spur to Stewart."),
    ("stewart", "Stewart", "town", "northern-bc", 55.938, -129.991, "corridor", False, True, False, ["Stewart"], "Port town at the head of Portland Canal, reached by Highway 37A."),
    ("kitwanga", "Kitwanga", "town", "northern-bc", 55.100, -128.067, "corridor", False, False, False, ["Kitwanga"], "Junction of the Cassiar Highway and Highway 16."),
    ("new-hazelton", "New Hazelton", "town", "northern-bc", 55.249, -127.586, "corridor", False, False, False, ["New Hazelton", "Hazelton"], "Highway 16 community east of Kitwanga."),
    ("smithers", "Smithers", "town", "northern-bc", 54.781, -127.168, "corridor", False, False, False, ["Smithers"], "Bulkley Valley town on Highway 16."),
    ("terrace", "Terrace", "town", "northern-bc", 54.516, -128.599, "corridor", False, True, False, ["Terrace"], "Skeena town on Highway 16 west of Kitwanga."),
    ("prince-rupert", "Prince Rupert", "town", "northern-bc", 54.315, -130.321, "adjacent", False, False, False, ["Prince Rupert"], "Coastal port at the west end of Highway 16."),
    ("burns-lake", "Burns Lake", "town", "northern-bc", 54.229, -125.763, "corridor", False, False, False, ["Burns Lake"], "Highway 16 community between Smithers and Vanderhoof."),
    ("vanderhoof", "Vanderhoof", "town", "northern-bc", 54.014, -124.008, "corridor", False, False, False, ["Vanderhoof"], "Highway 16 community west of Prince George."),
    ("northern-bc", "Northern British Columbia", "region", "northern-bc", 57.2, -129.4, "corridor", True, False, False, ["Northern British Columbia", "northern BC"], "Region covering the Cassiar Highway and the Highway 16 communities north and west of Prince George."),
    ("liard-river", "Liard River", "settlement", "northern-bc", 59.425, -126.105, "corridor", False, False, False, ["Liard River", "Liard Hot Springs"], "Alaska Highway settlement area near Liard River Hot Springs."),
    ("muncho-lake", "Muncho Lake", "settlement", "northern-bc", 58.998, -125.769, "corridor", False, False, False, ["Muncho Lake"], "Alaska Highway settlement beside Muncho Lake."),
    ("fort-nelson", "Fort Nelson", "town", "northern-bc", 58.805, -122.697, "corridor", False, False, False, ["Fort Nelson"], "Alaska Highway town in northeastern British Columbia."),
    ("fort-st-john", "Fort St. John", "town", "northern-bc", 56.252, -120.847, "corridor", False, False, False, ["Fort St. John", "Fort St John"], "Alaska Highway city south of Fort Nelson."),
    ("dawson-creek", "Dawson Creek", "town", "northern-bc", 55.7596, -120.2377, "corridor", False, False, False, ["Dawson Creek"], "Official start of the Alaska Highway, southeast of Fort St. John."),
    ("prince-george", "Prince George", "town", "southern-bc", 53.9171, -122.7497, "corridor", True, False, False, ["Prince George"], "Highway hub where the Alaska Highway, Highway 16, and Highway 97 meet."),
    ("quesnel", "Quesnel", "town", "southern-bc", 52.9784, -122.4927, "corridor", False, False, False, ["Quesnel"], "Cariboo city on Highway 97 south of Prince George."),
    ("williams-lake", "Williams Lake", "town", "southern-bc", 52.1417, -122.1445, "corridor", False, False, False, ["Williams Lake"], "Cariboo city on Highway 97."),
    ("cache-creek", "Cache Creek", "town", "southern-bc", 50.810, -121.324, "corridor", False, False, False, ["Cache Creek"], "Junction of Highway 97 and the Trans-Canada Highway."),
    ("hope", "Hope", "town", "southern-bc", 49.383, -121.441, "corridor", False, True, False, ["Hope"], "Fraser Canyon town on Highway 1 east of Vancouver."),
    ("vancouver", "Vancouver", "town", "southern-bc", 49.2827, -123.1207, "corridor", True, False, False, ["Vancouver"], "Coastal city at the south end of this atlas's initial corridor."),
    ("whistler", "Whistler", "town", "southern-bc", 50.1163, -122.9574, "adjacent", False, False, False, ["Whistler"], "Resort town on the Sea-to-Sky Highway north of Vancouver."),
    ("jasper", "Jasper", "town", "northern-bc", 52.8737, -118.0814, "adjacent", False, True, False, ["Jasper"], "Alberta park town east of the British Columbia highway network."),
    ("alaska-highway", "Alaska Highway", "highway", "yukon", 60.0, -135.0, "corridor", False, False, False, ["Alaska Highway", "Alcan Highway"], "Highway corridor from Dawson Creek to Delta Junction. The line on this map is schematic."),
    ("cassiar-highway", "Cassiar Highway", "highway", "northern-bc", 58.0, -129.8, "corridor", False, False, False, ["Cassiar Highway", "Highway 37"], "Highway 37 from Watson Lake to Kitwanga, an alternative to the Alaska Highway bend through Fort Nelson."),
]

# from_id, to_id, highway, role
SEGMENTS = [
    ("anchorage", "palmer", "Glenn Highway", "alternative"),
    ("palmer", "glennallen", "Glenn Highway", "alternative"),
    ("glennallen", "tok", "Tok Cut-Off", "alternative"),
    ("fairbanks", "delta-junction", "Richardson Highway", "alternative"),
    ("fairbanks", "denali", "Parks Highway", "alternative"),
    ("denali", "wasilla", "Parks Highway", "alternative"),
    ("wasilla", "anchorage", "Parks Highway", "alternative"),
    ("delta-junction", "tok", "Alaska Highway", "spine"),
    ("tok", "chicken", "Taylor Highway", "spur"),
    ("tok", "northway", "Alaska Highway", "spine"),
    ("northway", "port-alcan", "Alaska Highway", "spine"),
    ("port-alcan", "beaver-creek", "Alaska Highway", "spine"),
    ("beaver-creek", "destruction-bay", "Alaska Highway", "spine"),
    ("destruction-bay", "haines-junction", "Alaska Highway", "spine"),
    ("haines-junction", "whitehorse", "Alaska Highway", "spine"),
    ("haines-junction", "haines", "Haines Highway", "spur"),
    ("whitehorse", "carcross", "Klondike Highway", "spur"),
    ("carcross", "skagway", "Klondike Highway", "spur"),
    ("whitehorse", "teslin", "Alaska Highway", "spine"),
    ("teslin", "watson-lake", "Alaska Highway", "spine"),
    ("watson-lake", "liard-river", "Alaska Highway", "spine"),
    ("liard-river", "muncho-lake", "Alaska Highway", "spine"),
    ("muncho-lake", "fort-nelson", "Alaska Highway", "spine"),
    ("fort-nelson", "fort-st-john", "Alaska Highway", "spine"),
    ("fort-st-john", "dawson-creek", "Alaska Highway", "spine"),
    ("dawson-creek", "prince-george", "Alaska Highway", "spine"),
    ("watson-lake", "dease-lake", "Cassiar Highway", "alternative"),
    ("dease-lake", "iskut", "Cassiar Highway", "alternative"),
    ("iskut", "meziadin", "Cassiar Highway", "alternative"),
    ("meziadin", "stewart", "Highway 37A", "spur"),
    ("meziadin", "kitwanga", "Cassiar Highway", "alternative"),
    ("kitwanga", "new-hazelton", "Highway 16", "alternative"),
    ("new-hazelton", "smithers", "Highway 16", "alternative"),
    ("smithers", "burns-lake", "Highway 16", "alternative"),
    ("burns-lake", "vanderhoof", "Highway 16", "alternative"),
    ("vanderhoof", "prince-george", "Highway 16", "alternative"),
    ("kitwanga", "terrace", "Highway 16", "spur"),
    ("terrace", "prince-rupert", "Highway 16", "spur"),
    ("prince-george", "quesnel", "Highway 97", "spine"),
    ("quesnel", "williams-lake", "Highway 97", "spine"),
    ("williams-lake", "cache-creek", "Highway 97", "spine"),
    ("cache-creek", "hope", "Trans-Canada Highway", "spine"),
    ("hope", "vancouver", "Trans-Canada Highway", "spine"),
    ("vancouver", "whistler", "Sea-to-Sky Highway", "spur"),
]

BICYCLE_NOTE = (
    "A line on this map connects named places along a public highway. "
    "It does not mean the road is safe, open, paved, or legally rideable by bicycle."
)
SURFACE_NOTE = "Surface type, shoulder width, and traffic are not verified in this reference set."

AGENCIES = [
    {
        "id": "ak511",
        "title": "Alaska 511",
        "url": "https://511.alaska.gov/",
        "publisher": "Alaska Department of Transportation and Public Facilities",
        "regions": ["alaska"],
        "topics": ["road_conditions", "closures", "construction"],
    },
    {
        "id": "yukon511",
        "title": "511 Yukon",
        "url": "https://511yukon.ca/",
        "publisher": "Government of Yukon",
        "regions": ["yukon"],
        "topics": ["road_conditions", "closures", "construction"],
    },
    {
        "id": "drivebc",
        "title": "DriveBC",
        "url": "https://www.drivebc.ca/",
        "publisher": "British Columbia Ministry of Transportation and Transit",
        "regions": ["northern-bc", "southern-bc"],
        "topics": ["road_conditions", "closures", "construction"],
    },
    {
        "id": "cbp",
        "title": "U.S. Customs and Border Protection",
        "url": "https://www.cbp.gov/",
        "publisher": "U.S. Customs and Border Protection",
        "regions": ["border"],
        "topics": ["border", "legal"],
    },
    {
        "id": "cbsa",
        "title": "Canada Border Services Agency",
        "url": "https://www.cbsa-asfc.gc.ca/",
        "publisher": "Canada Border Services Agency",
        "regions": ["border"],
        "topics": ["border", "legal"],
    },
]


def location_by_id(location_id: str) -> dict | None:
    for row in LOCATIONS:
        if row[0] == location_id:
            return location_record(row)
    return None


def location_record(row: tuple) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "kind": row[2],
        "region_id": row[3],
        "lat": row[4],
        "lon": row[5],
        "scope": row[6],
        "featured": row[7],
        "ambiguous": row[8],
        "border_community": row[9],
        "aliases": list(row[10]),
        "summary": row[11],
    }


def all_locations() -> list[dict]:
    return [location_record(row) for row in LOCATIONS]


def highways_touching(location_id: str) -> list[str]:
    names = []
    for src, dst, highway, _role in SEGMENTS:
        if location_id in (src, dst) and highway not in names:
            names.append(highway)
    return names
