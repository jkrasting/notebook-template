import copy
import datetime as dt

import intake_esm
import pytest

import esnb
from esnb import CaseExperiment2
from esnb.core.util2 import (
    case_time_filter,
    check_schema_equivalence,
    initialize_cases_from_source,
    merge_intake_catalogs,
    reset_catalog_metadata,
    update_intake_dataframe,
    xr_date_range_to_datetime,
)

source1 = "tests/test_data/intake-uda-cmip.json"
source2 = "tests/test_data/input_timeslice_test.yml"
source3 = "895"

catalog1 = "tests/test_data/intake-uda-cmip.json"
catalog2 = "https://storage.googleapis.com/cmip6/pangeo-cmip6.json"

cat1 = intake_esm.esm_datastore("https://dora.gfdl.noaa.gov/api/intake/1188.json")
cat2 = intake_esm.esm_datastore("https://dora.gfdl.noaa.gov/api/intake/1243.json")
cat3 = intake_esm.esm_datastore("https://dora.gfdl.noaa.gov/api/intake/1183.json")
cat4 = intake_esm.esm_datastore(catalog1)
cat5 = intake_esm.esm_datastore(catalog2)


def test_case_time_filter():
    _source3 = copy.deepcopy(source3)
    case = CaseExperiment2(_source3)
    date_range = ("0041-01-01", "0060-12-31")
    n_times_start = int(case.catalog.nunique()["time_range"])
    df = case_time_filter(case, date_range)
    n_times_end = int(case.catalog.nunique()["time_range"])
    print(n_times_start, n_times_end)
    assert n_times_end < n_times_start


def test_check_schema_equivalence_1():
    _cat4 = copy.deepcopy(cat4)
    assert check_schema_equivalence(_cat4, _cat4)


def test_check_schema_equivalence_2():
    _cat4 = copy.deepcopy(cat4)
    _cat5 = copy.deepcopy(cat5)
    assert not check_schema_equivalence(_cat4, _cat5)


def test_initialize_cases_from_source():
    _source1 = copy.deepcopy(source1)
    _source2 = copy.deepcopy(source2)
    source = [_source1, [_source2, _source2]]
    groups = initialize_cases_from_source(source)
    assert isinstance(groups, list)
    assert isinstance(groups[1], list)
    assert all(
        isinstance(x, esnb.core.CaseExperiment2.CaseExperiment2)
        for x in groups[1] + [groups[0]]
    )


def test_merge_intake_catalogs_1():
    _cat1 = copy.deepcopy(cat1)
    catalogs = _cat1
    result = merge_intake_catalogs(catalogs)


def test_merge_intake_catalogs_2():
    _cat1 = copy.deepcopy(cat1)
    _cat4 = copy.deepcopy(cat4)
    catalogs = [_cat1, _cat4]
    # result = merge_intake_catalogs(catalogs, **kwargs)


def test_merge_intake_catalogs_3():
    _cat1 = copy.deepcopy(cat1)
    _cat2 = copy.deepcopy(cat2)
    _cat3 = copy.deepcopy(cat3)
    catalogs = [_cat1, _cat2, _cat3]
    result = merge_intake_catalogs(catalogs, id="merged catalog")


def test_reset_catalog_metadata():
    _cat = copy.deepcopy(cat4)
    original_name = str(_cat.esmcat.id)
    original_time = dt.datetime(*tuple(_cat.esmcat.last_updated.timetuple())[0:7])
    print(original_name, original_time)
    new_id = "new catalog"
    newcat = reset_catalog_metadata(_cat, id=new_id)
    new_name = str(newcat.esmcat.id)
    new_time = dt.datetime(*tuple(newcat.esmcat.last_updated.timetuple())[0:7])
    assert new_time > original_time
    assert new_name != original_name
    assert new_name == new_id


def test_update_intake_dataframe():
    _cat = copy.deepcopy(cat4)
    df = _cat.df
    df = df[:123]
    updated_cat = update_intake_dataframe(_cat, df)


def test_xr_date_range_to_datetime():
    date_range = ("0041-01-01", "0060-12-31")
    assert xr_date_range_to_datetime(date_range) == (
        dt.datetime(41, 1, 1),
        dt.datetime(60, 12, 31),
    )
