import pandas as pd

from climaguard.blocks import actions, match_unit, point_in, vulnerability
from climaguard.idsp import block_of

SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]}


def test_point_in_polygon():
    assert point_in(1, 1, SQUARE)
    assert not point_in(3, 1, SQUARE)
    assert point_in(1, 1, {"type": "MultiPolygon", "coordinates": [[[[5, 5], [6, 5], [6, 6], [5, 5]]], SQUARE["coordinates"]]})


def test_block_name_from_report_text():
    assert block_of("Cases reported from Village/HSC A. Kalayamputhur, PHC Neikarapatti, Block Palani. District RRT") == "Palani"
    assert block_of("Village Sadaiyaneri, Block Mudukulathur, PHC Theriruveli") == "Mudukulathur"
    assert block_of("Cases reported from Ward 12, Chennai Corporation.") is None


def test_fuzzy_unit_match():
    units = ["Udhagamandalam", "Coonoor", "Kotagiri"]
    assert match_unit("Coonnoor", units) == "Coonoor"
    assert match_unit("Kariyapatti", units) is None


def test_vulnerability_ranks_within_district():
    u = pd.DataFrame({"district_id": [1, 1, 1, 2], "density": [100, 900, 500, 5],
                      "child_share": [0.08, 0.12, 0.10, 0.01], "past_outbreaks": [0, 2, 0, 0]})
    v, pct = vulnerability(u)
    assert v.iloc[1] == 1.0                      # densest, most children, only past outbreak
    assert v.iloc[0] < v.iloc[2] < v.iloc[1]
    assert v.iloc[3] == 1.0                      # alone in its district: ranked only against itself


def test_every_unit_gets_an_action():
    quiet = actions({"past_outbreaks": 0}, {"density": 0.1, "child_share": 0.1})
    busy = actions({"past_outbreaks": 2}, {"density": 0.9, "child_share": 0.9})
    assert len(quiet) == 1 and "stored water" in quiet[0]
    assert len(busy) == 4 and busy[0].startswith("Dengue outbreak reported here before (2×)")
