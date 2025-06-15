import copy
import datetime as dt
import logging
import time

import intake_esm
import pandas as pd

import esnb
from esnb.core.CaseExperiment2 import CaseExperiment2
from esnb.core.util import is_overlapping, process_time_string

logger = logging.getLogger("__name__")


def case_time_filter(case, date_range):
    assert len(date_range) == 2
    trange = xr_date_range_to_datetime(date_range)
    df = case.catalog.df
    non_matching_times = []
    for index, row in df.iterrows():
        if not is_overlapping(trange, row["time_range"]):
            non_matching_times.append(index)
    df = df.drop(non_matching_times)
    case.catalog.esmcat._df = df
    return df


def check_schema_equivalence(esmcat1, esmcat2, keys=None):
    """Access the lower level catalog definitions to see if they are the same"""
    # esmcat keys:  ['esmcat_version',
    #                'attributes',
    #                'assets',
    #                'aggregation_control',
    #                'id',
    #                'catalog_dict',
    #                'catalog_file',
    #                'description',
    #                'title',
    #                'last_updated']

    # Default set of keys to check for equivalence
    keys = ["attributes", "aggregation_control"] if keys is None else keys

    # Access each catalog's `esmcat` dictionary
    cat1 = esmcat1.__dict__["esmcat"].__dict__
    cat2 = esmcat2.__dict__["esmcat"].__dict__

    return all([cat1[k] == cat2[k] for k in keys])


def flatten_list(nested_list):
    flat_list = []
    for item in nested_list:
        if isinstance(item, list):
            flat_list.extend(flatten_list(item))  # Recursive call
        else:
            flat_list.append(item)
    return flat_list


def initialize_cases_from_source(source):
    if not isinstance(source, list):
        err = f"Sources provided to `initialize_cases_from_source` must be a list"
        logger.error(err)
        raise ValueError(err)

    groups = []
    for x in source:
        if not isinstance(x, list):
            logging.debug(f"Setting up individual case/experiment: {x}")
            groups.append(CaseExperiment2(x))
        else:
            subgroup = []
            for i in x:
                if isinstance(i, list):
                    err = "Only two levels of case aggregation are supported."
                    logging.error(err)
                    raise NotImplementedError(err)
                else:
                    logging.debug(f"Setting up individual case/experiment: {i}")
                    subgroup.append(CaseExperiment2(i))
            groups.append(subgroup)

    return groups


def merge_intake_catalogs(catalogs, id=None, description=None, title=None, **kwargs):
    # catalogs is a list of catalogs
    catalogs = [catalogs] if not isinstance(catalogs, list) else catalogs
    if len(catalogs) == 1:
        result = catalogs[0]
    else:
        # test that catalogs are equivalent
        equivalence = [check_schema_equivalence(catalogs[0], x) for x in catalogs]
        assert all(equivalence), f"All catalogs must have the same schema to merge"

        # obtain the underlying dataframes
        dfs = [x.df for x in catalogs]

        # merge subsequent catalogs onto the first
        merged_df = copy.deepcopy(dfs[0])

        for df in dfs[1:]:
            # Use pandas.merge() function and pass options, if provided
            kwargs = {"how": "outer"} if kwargs == {} else kwargs
            merged_df = pd.merge(merged_df, df, **kwargs)

        result = copy.deepcopy(catalogs[0])
        result = update_intake_dataframe(result, merged_df)
        result = reset_catalog_metadata(
            result, id=id, description=description, title=title
        )

    return result


def reset_catalog_metadata(cat, id=None, description=None, title=None):
    id = "" if id is None else str(id)
    description = "" if description is None else str(description)
    title = "" if title is None else str(title)
    cat.__dict__["_captured_init_args"] = None
    cat.__dict__["updated"] = time.time()
    cat.__dict__["esmcat"].__dict__["last_updated"] = dt.datetime.fromtimestamp(
        cat.__dict__["updated"], dt.UTC
    )
    cat.__dict__["esmcat"].__dict__["catalog_file"] = None
    cat.__dict__["esmcat"].__dict__["id"] = id
    cat.__dict__["esmcat"].__dict__["description"] = description
    cat.__dict__["esmcat"].__dict__["title"] = title
    return cat


def update_intake_dataframe(cat, df, reset_index=True):
    if reset_index:
        df = df.reset_index()
    cat.esmcat._df = df
    return cat


def xr_date_range_to_datetime(date_range):
    _date_range = []
    for x in date_range:
        x = x.split("-")
        x = str(x[0]).zfill(4) + str(x[1]).zfill(2) + str(x[2].zfill(2))
        _date_range.append(x)
    _date_range = str("-").join(_date_range)
    _date_range = process_time_string(_date_range)
    return _date_range
