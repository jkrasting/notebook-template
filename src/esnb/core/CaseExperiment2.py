import json
import logging
from pathlib import Path

import intake
import intake_esm
from esnb import sites
from esnb.core.mdtf import MDTFCaseSettings

from . import html
from . import util

logger = logging.getLogger(__name__)


def infer_case_source(source):
    """
    Infer the source type from the input.
    Args:
        source (str, int, Path): The source input which can be a path to an intake_esm catalog,
                                 MDTF settings file, or a DORA ID.
    Returns:
        str: The mode of the source, which can be "intake_path", "intake_url", "dora_id", or "dora_url"
    """

    if isinstance(source, str):
        if source.isnumeric():
            logger.debug(f"Found source string with numeric Dora ID - {source}")
            mode = "dora_id"
        elif source.startswith("http") or source.startswith("https"):
            if "dora.gfdl" in source:
                logger.debug(f"Found source url pointing to Dora - {source}")
                mode = "dora_url"
            else:
                logger.debug(f"Found source url suggesting intake catalog - {source}")
                mode = "intake_url"
        elif "-" in source:
            if source.split("-")[1].isnumeric():
                logger.debug(
                    f"Found source string with project-level dora ID - {source}"
                )
                mode = "dora_id"
            else:
                mode = "path"
        else:
            mode = "path"
    elif isinstance(source, int):
        logger.debug(f"Found source integer suggesting dora ID - {source}")
        mode = "dora_id"
    else:
        raise ValueError(
            "Unsupported source type. Must be path or url to"
            + " intake_esm catalog, MDTF settings file, or DORA ID"
        )

    if mode == "path":
        logger.debug(f"Assuming source is a local file path - {source}")
        filepath = Path(source)
        if not filepath.exists():
            logger.error(f"Path {filepath} does not exist")
            raise FileNotFoundError(f"Path {filepath} does not exist")
        if filepath.is_dir():
            mode = "pp_dir"
            logger.debug(
                f"Supplied path appears to be a directory, possibly containing post-processing"
            )
            err = f"The supplied path is a directory. In the future, support will be added to generate a catalog."
            logger.error(err)
            raise NotImplementedError(err)
        else:
            try:
                with open(filepath, "r") as f:
                    json.load(f)
                logger.debug(
                    f"Source appears to be a JSON file, assuming intake catalog"
                )
                mode = "intake_path"
            except json.JSONDecodeError:
                logger.debug(f"Source is not a JSON file, assuming MDTF settings file")
                mode = "mdtf_settings"

    return mode


def open_intake_catalog(source, mode):
    if mode == "intake_url":
        logger.info(f"Fetching intake catalog from url: {source}")
        catalog = intake.open_esm_datastore(source)

    elif mode == "intake_path":
        logger.info(f"Opening intake catalog from file: {source}")
        catalog = intake.open_esm_datastore(source)

    else:
        err = f"Encountered unrecognized source mode: {mode}"
        loggger.error(err)
        raise RuntimeError(err)

    return catalog


def open_intake_catalog_dora(source, mode):
    if mode == "dora_url":
        url = source
    elif mode == "dora_id":
        url = f"https://{sites.gfdl.dora_hostname}/api/intake/{source}.json"
    else:
        err = f"Encountered unrecognized source mode: {mode}"
        loggger.error(err)
        raise RuntimeError(err)

    logger.info(f"Fetching intake catalog from url: {url}")
    if not sites.gfdl.dora:
        logger.critical(f"Network route to dora is unavailble. Check connection.")
    catalog = intake.open_esm_datastore(url)

    return catalog


class CaseExperiment2(MDTFCaseSettings):
    def __init__(self, source, verbose=True):
        self.source = source
        self.mode = infer_case_source(self.source)

        # Read the MDTF settings case file
        if self.mode == "mdtf_settings":
            logger.info("Loading MDTF Settings File")
            self.load_mdtf_settings_file(source)
            if len(self.mdtf_settings["case_list"]) == 0:
                raise ValueError("No cases found in MDTF settings file")
            elif len(self.mdtf_settings["case_list"]) > 1:
                raise ValueError(
                    "Multiple cases found in MDTF settings file. "
                    + "Please initialize using the `CaseGroup` class."
                )
            self.name = list(self.mdtf_settings["case_list"].keys())[0]

            catalog_file = Path(self.catalog)
            logger.debug(
                f"Loading intake catalog from path specified in MDTF settings file: {str(catalog_file)}"
            )
            if catalog_file.exists():
                self.catalog = open_intake_catalog(str(catalog_file), "intake_path")
            else:
                logger.warning(
                    f"MDTF-specified intake catalog path does not exist: {str(catalog_file)}"
                )

        elif "intake" in self.mode or "dora" in self.mode:
            if "intake" in self.mode:
                self.catalog = open_intake_catalog(self.source, self.mode)
            elif "dora" in self.mode:
                self.catalog = open_intake_catalog_dora(self.source, self.mode)
            self.name = self.catalog.__dict__["esmcat"].__dict__["id"]

        else:
            err = f"Encountered unrecognized source mode: {mode}"
            loggger.error(err)
            raise RuntimeError(err)

        # Convert catalog `time_range` to tuple of datetime objects
        if isinstance(self.catalog, intake_esm.core.esm_datastore):
            logger.debug(
                f"Converting time range in {self.name} catalog to datetime object"
            )
            self.catalog.df["time_range"] = self.catalog.df["time_range"].apply(
                util.process_time_string
            )

    def _repr_html_(self):
        result = html.gen_html_sub()
        # Table Header
        result += f"<h3>{self.__class__.__name__}  --  {self.name}</h3>"
        result += "<table class='cool-class-table'>"

        # Iterate over attributes, handling the dictionary separately
        result += f"<tr><td><strong>Source Type</strong></td><td>{self.mode}</td></tr>"
        result += f"<tr><td><strong>catalog</strong></td><td>{str(self.catalog).replace('<', '').replace('>', '')}</td></tr>"
        # for key in sorted(self.__dict__.keys()):
        #    value = str(self.__dict__[key])
        #    if key == 'mdtf_settings':
        #        continue
        #    result += f"<tr><td><strong>{key}</strong></td><td>{value}</td></tr>"

        if hasattr(self, "mdtf_settings"):
            result += "<tr><td colspan='2'>"
            result += "<details>"
            result += "<summary>View MDTF Settings</summary>"
            result += "<div><table>"
            for d_key in sorted(self.mdtf_settings.keys()):
                d_value = self.mdtf_settings[d_key]
                result += f"<tr><td>{d_key}</td><td>{d_value}</td></tr>"
            result += "</table></div>"
            result += "</details>"
            result += "</td></tr>"

        result += "</table>"

        return result
