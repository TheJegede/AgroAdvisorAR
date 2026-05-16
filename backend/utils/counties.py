# Arkansas county FIPS codes → (county_name, centroid_lat, centroid_lon, ssurgo_areasymbol)
# FIPS format: "05XXX" where XXX is 3-digit county code
# areasymbol: "AR" + last 3 digits of FIPS

AR_COUNTIES = {
    "05001": ("Arkansas County",    34.2920, -91.3731, "AR001"),
    "05003": ("Ashley County",      33.1927, -91.7778, "AR003"),
    "05005": ("Baxter County",      36.2750, -92.3542, "AR005"),
    "05007": ("Benton County",      36.3378, -94.2096, "AR007"),
    "05009": ("Boone County",       36.3501, -93.0932, "AR009"),
    "05011": ("Bradley County",     33.4599, -92.1534, "AR011"),
    "05013": ("Calhoun County",     33.5657, -92.5082, "AR013"),
    "05015": ("Carroll County",     36.3467, -93.5337, "AR015"),
    "05017": ("Chicot County",      33.2706, -91.2952, "AR017"),
    "05019": ("Clark County",       34.0550, -93.1761, "AR019"),
    "05021": ("Clay County",        36.3732, -90.4287, "AR021"),
    "05023": ("Cleburne County",    35.5186, -92.0318, "AR023"),
    "05025": ("Cleveland County",   33.8977, -92.2101, "AR025"),
    "05027": ("Columbia County",    33.2219, -93.1501, "AR027"),
    "05029": ("Conway County",      35.2606, -92.6882, "AR029"),
    "05031": ("Craighead County",   35.8317, -90.6393, "AR031"),
    "05033": ("Crawford County",    35.5751, -94.2404, "AR033"),
    "05035": ("Crittenden County",  35.2099, -90.3001, "AR035"),
    "05037": ("Cross County",       35.2812, -90.7656, "AR037"),
    "05039": ("Dallas County",      33.9761, -92.6360, "AR039"),
    "05041": ("Desha County",       33.8286, -91.2269, "AR041"),
    "05043": ("Drew County",        33.5729, -91.7227, "AR043"),
    "05045": ("Faulkner County",    35.1463, -92.3454, "AR045"),
    "05047": ("Franklin County",    35.5287, -93.8768, "AR047"),
    "05049": ("Fulton County",      36.3814, -91.8148, "AR049"),
    "05051": ("Garland County",     34.5720, -93.1522, "AR051"),
    "05053": ("Grant County",       34.2886, -92.4217, "AR053"),
    "05055": ("Greene County",      36.1114, -90.5376, "AR055"),
    "05057": ("Hempstead County",   33.7299, -93.6704, "AR057"),
    "05059": ("Hot Spring County",  34.3145, -92.9513, "AR059"),
    "05061": ("Howard County",      34.0827, -93.9934, "AR061"),
    "05063": ("Independence County",35.7399, -91.5726, "AR063"),
    "05065": ("Izard County",       36.0865, -91.9025, "AR065"),
    "05067": ("Jackson County",     35.5979, -91.2121, "AR067"),
    "05069": ("Jefferson County",   34.2726, -91.9263, "AR069"),
    "05071": ("Johnson County",     35.5621, -93.4506, "AR071"),
    "05073": ("Lafayette County",   33.2186, -93.6104, "AR073"),
    "05075": ("Lawrence County",    36.0375, -91.1124, "AR075"),
    "05077": ("Lee County",         34.7760, -90.7845, "AR077"),
    "05079": ("Lincoln County",     33.9566, -91.7335, "AR079"),
    "05081": ("Little River County",33.7041, -94.2264, "AR081"),
    "05083": ("Logan County",       35.2201, -93.7188, "AR083"),
    "05085": ("Lonoke County",      34.7556, -91.8965, "AR085"),
    "05087": ("Madison County",     36.0163, -93.7274, "AR087"),
    "05089": ("Marion County",      36.2848, -92.6773, "AR089"),
    "05091": ("Miller County",      33.3135, -93.9085, "AR091"),
    "05093": ("Mississippi County", 35.7639, -90.0613, "AR093"),
    "05095": ("Monroe County",      34.6790, -91.2025, "AR095"),
    "05097": ("Montgomery County",  34.5439, -93.6588, "AR097"),
    "05099": ("Nevada County",      33.6614, -93.3155, "AR099"),
    "05101": ("Newton County",      35.9330, -93.2130, "AR101"),
    "05103": ("Ouachita County",    33.5978, -92.8735, "AR103"),
    "05105": ("Perry County",       35.0715, -92.9200, "AR105"),
    "05107": ("Phillips County",    34.4358, -90.8296, "AR107"),
    "05109": ("Pike County",        34.1646, -93.6561, "AR109"),
    "05111": ("Poinsett County",    35.5730, -90.6479, "AR111"),
    "05113": ("Polk County",        34.4793, -94.2196, "AR113"),
    "05115": ("Pope County",        35.4509, -93.0421, "AR115"),
    "05117": ("Prairie County",     34.9933, -91.5544, "AR117"),
    "05119": ("Pulaski County",     34.7695, -92.3086, "AR119"),
    "05121": ("Randolph County",    36.3446, -91.0286, "AR121"),
    "05123": ("St. Francis County", 35.0241, -90.7538, "AR123"),
    "05125": ("Saline County",      34.6453, -92.6681, "AR125"),
    "05127": ("Scott County",       34.8628, -94.0586, "AR127"),
    "05129": ("Searcy County",      35.9283, -92.6946, "AR129"),
    "05131": ("Sebastian County",   35.1947, -94.2785, "AR131"),
    "05133": ("Sevier County",      33.9930, -94.2472, "AR133"),
    "05135": ("Sharp County",       36.1578, -91.4878, "AR135"),
    "05137": ("Stone County",       35.8641, -92.1471, "AR137"),
    "05139": ("Union County",       33.1756, -92.5914, "AR139"),
    "05141": ("Van Buren County",   35.5680, -92.5337, "AR141"),
    "05143": ("Washington County",  35.9780, -94.2151, "AR143"),
    "05145": ("White County",       35.2545, -91.7445, "AR145"),
    "05147": ("Woodruff County",    35.1855, -91.2427, "AR147"),
    "05149": ("Yell County",        35.0016, -93.4078, "AR149"),
}


def get_county_info(fips: str) -> dict | None:
    entry = AR_COUNTIES.get(fips)
    if not entry:
        return None
    name, lat, lon, areasymbol = entry
    return {
        "county_name": name,
        "lat": lat,
        "lon": lon,
        "areasymbol": areasymbol,
        "fips": fips,
    }


def fips_to_areasymbol(fips: str) -> str:
    """Convert FIPS like '05055' to SSURGO areasymbol like 'AR055'."""
    info = AR_COUNTIES.get(fips)
    if info:
        return info[3]
    # Fallback: construct from FIPS digits
    return "AR" + fips[2:]
