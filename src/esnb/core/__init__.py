import datetime
import re
import subprocess

import intake_esm
import pandas as pd
import xarray as xr
import yaml

try:
    import doralite
except:
    pass


from . import util2


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def clean_string(input_string):
    res = re.sub(r"[^a-zA-Z0-9\s]", "", input_string)
    res = res.replace(" ", "_")
    res = re.sub(r"_+", "_", res)
    return res


def xr_date_range_format(date_range):
    date_range = list(date_range)
    date_range = [str(x) for x in date_range]
    predicate = ["-01-01", "-12-31"]
    for x, tstr in enumerate(date_range):
        if len(tstr) <= 4:
            date_range[x] = date_range[x].zfill(4) + predicate[x]
    return date_range


def call_dmget(files, verbose=False):
    files = [files] if not isinstance(files, list) else files
    totalfiles = len(files)
    result = subprocess.run(["dmls", "-l"] + files, capture_output=True, text=True)
    result = result.stdout.splitlines()
    result = [x.split(" ")[-5:] for x in result]
    result = [(x[-1], int(x[0])) for x in result if x[-2] == "(OFL)"]

    if len(result) == 0:
        if verbose:
            print("dmget: All files are online")
    else:
        numfiles = len(result)
        paths, sizes = zip(*result)
        totalsize = round(sum(sizes) / 1024 / 1024, 1)
        if verbose:
            print(
                f"dmget: Dmgetting {numfiles} of {totalfiles} files requested ({totalsize} MB)"
            )
        cmd = ["dmget"] + paths
        _ = subprocess.check_output(cmd)


def case_groups_catalogs(case_groups, diag_settings):
    grp_catalogs = []
    date_ranges = []
    for k, v in case_groups.items():
        idnums = v["idnums"].replace(" ", "").split(",")
        catalogs = [load_dora_catalog(x) for x in idnums]
        if len(catalogs) > 1:
            catalog = catalogs[0].merge(catalogs[1:])
        else:
            catalog = catalogs[0]
        grp_catalogs.append(catalog)
        date_ranges.append(v["date_range"])

    for n, cat in enumerate(grp_catalogs):
        subcats = []
        for k, v in diag_settings["varlist"].items():
            subcat = cat.find(
                var=k,
                kind=v["ppkind"],
                preferred_chunkfreq=v["preferred_chunkfreq"],
                freq=v["freq"],
                preferred_realm=v["preferred_realm"],
            )
            subcats.append(subcat)
        if len(subcats) > 1:
            catalog = subcats[0].merge(subcats[1:])
        else:
            catalog = subcats[0]
        grp_catalogs[n] = catalog

    for n, v in enumerate(date_ranges):
        grp_catalogs[n] = reindex_catalog(grp_catalogs[n].find(trange=tuple(v)))

    return grp_catalogs


def consolidate_datasets(dset_dict):
    all_dsets = [v for _, v in dset_dict.items()]
    consolidated = []
    consolidated.append(all_dsets.pop(0))
    while len(all_dsets) > 0:
        n_consolidated = len(consolidated)
        candidate = all_dsets[0]
        for x in range(0, n_consolidated):
            merged = False
            try:
                _ds = xr.merge([consolidated[x], candidate], compat="no_conflicts")
                merged = True
            except:
                continue

            if merged:
                consolidated[x] = _ds
                _ = all_dsets.pop(0)
                break

        if len(all_dsets) > 0:
            consolidated.append(all_dsets.pop(0))
    assert len(all_dsets) == 0, "Consolidation failed -- some datasets left over"
    return consolidated


def copy_catalog(cat):
    _source = cat.source_catalog()
    _source["df"] = cat.df.copy()
    return Dora_datastore(_source)


def df_to_cat(df, label=""):
    for key in [
        "source_id",
        "experiment_id",
        "frequency",
        "table_id",
        "grid_label",
        "realm",
        "member_id",
        "chunk_freq",
    ]:
        df[key] = df[key].fillna("unknown")

    esmcat_memory = {
        "esmcat": {  # <== Metadata only here
            "esmcat_version": "0.0.1",
            "attributes": [
                {"column_name": "activity_id", "vocabulary": "", "required": False},
                {"column_name": "institution_id", "vocabulary": "", "required": False},
                {"column_name": "source_id", "vocabulary": "", "required": False},
                {"column_name": "experiment_id", "vocabulary": "", "required": True},
                {
                    "column_name": "frequency",
                    "vocabulary": "https://raw.githubusercontent.com/NOAA-GFDL/CMIP6_CVs/master/CMIP6_frequency.json",
                    "required": True,
                },
                {"column_name": "realm", "vocabulary": "", "required": True},
                {"column_name": "table_id", "vocabulary": "", "required": False},
                {"column_name": "member_id", "vocabulary": "", "required": False},
                {"column_name": "grid_label", "vocabulary": "", "required": False},
                {"column_name": "variable_id", "vocabulary": "", "required": True},
                {"column_name": "time_range", "vocabulary": "", "required": True},
                {"column_name": "chunk_freq", "vocabulary": "", "required": False},
                {"column_name": "platform", "vocabulary": "", "required": False},
                {"column_name": "target", "vocabulary": "", "required": False},
                {
                    "column_name": "cell_methods",
                    "vocabulary": "",
                    "required": False,
                },  # Adjusted from "enhanced" -> False
                {"column_name": "path", "vocabulary": "", "required": True},
                {
                    "column_name": "dimensions",
                    "vocabulary": "",
                    "required": False,
                },  # Adjusted from "enhanced" -> False
                {"column_name": "version_id", "vocabulary": "", "required": False},
                {
                    "column_name": "standard_name",
                    "vocabulary": "",
                    "required": False,
                },  # Adjusted from "enhanced" -> False
            ],
            "assets": {
                "column_name": "path",
                "format": "netcdf",
                "format_column_name": None,
            },
            "aggregation_control": {
                "variable_column_name": "variable_id",
                "groupby_attrs": [
                    "source_id",
                    "experiment_id",
                    "frequency",
                    "table_id",
                    "grid_label",
                    "realm",
                    "member_id",
                    "chunk_freq",
                ],
                "aggregations": [
                    {"type": "union", "attribute_name": "variable_id", "options": {}},
                    {
                        "type": "join_existing",
                        "attribute_name": "time_range",
                        "options": {
                            "dim": "time",
                            "coords": "minimal",
                            "compat": "override",
                        },
                    },
                ],
            },
            "id": label,
            "description": label,
            "title": label,
            "last_updated": datetime.datetime.now().isoformat(),
            "catalog_file": "dummy.csv",
        },
        "df": df,  # <== Your loaded DataFrame
    }

    return intake_esm.esm_datastore(esmcat_memory)


def infer_av_files(cat, subcat):
    avlist = [
        "ann",
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
        "09",
        "10",
        "11",
        "12",
    ]
    for var in subcat.vars:
        _subcat = cat.search(variable_id=var)
        for realm in _subcat.realms:
            varentry = _subcat.search(realm=realm).df.iloc[0]
            df = cat.search(variable_id=avlist).df
            df = df[df["path"].str.contains(f"/{realm}/")]
            for k in [
                "source_id",
                "experiment_id",
                "frequency",
                "realm",
                "variable_id",
            ]:
                df[k] = varentry[k]
            df["cell_methods"] = "av"
            df["standard_name"] = varentry["standard_name"]
            df["chunk_freq"] = df["chunk_freq"].str.replace("monthly_", "", regex=False)
            df["chunk_freq"] = df["chunk_freq"].str.replace("annual_", "", regex=False)
            df = df.reindex()
            _subcat = _subcat.merge(df_to_cat(df))
    return _subcat


def is_overlapping(period_a, period_b):
    start_a, end_a = period_a
    start_b, end_b = period_b
    if start_b is None or end_b is None:
        res = False
    else:
        res = start_a < end_b and end_a > start_b
    return res


def load_dora_catalog(idnum, **kwargs):
    return Dora_datastore(
        doralite.catalog(idnum).__dict__["_captured_init_args"][0], **kwargs
    )


def process_time_string(tstring):
    if isinstance(tstring, tuple):
        try:
            for x in tstring:
                assert isinstance(x, datetime.datetime) or x is None
            timetup = tstring
        except:
            timetup = (None, None)
    else:
        try:
            tstring = str(tstring)
            timetup = [x.ljust(8, "0") for x in tstring.split("-")]
            timetup = [[x[0:4], x[4:6], x[6:8]] for x in timetup]
            timetup[0][0] = int(timetup[0][0])
            timetup[0][1] = 1 if timetup[0][1] == "00" else int(timetup[0][1])
            timetup[0][2] = 1 if timetup[0][2] == "00" else int(timetup[0][2])
            timetup[1][0] = int(timetup[1][0])
            timetup[1][1] = 12 if timetup[1][1] == "00" else int(timetup[1][1])
            timetup[1][2] = 31 if timetup[1][2] == "00" else int(timetup[1][2])
            timetup = [tuple(x) for x in timetup]
            timetup = tuple([datetime.datetime(*x) for x in timetup])
        except:
            timetup = (None, None)

    return timetup


def reindex_catalog(cat):
    _source = cat.source_catalog()
    df = cat.df.copy()
    df = df.drop_duplicates("path")
    df = df.reset_index()
    _source["df"] = df
    return Dora_datastore(_source)
