from __future__ import annotations

import os
from pathlib import Path

import dlt

from nfs_fortaleza.config import Settings
from nfs_fortaleza.nfse_xml import nfse_xml_resource
from nfs_fortaleza.periods import DateRangePeriod, MonthPeriod


QueryPeriod = MonthPeriod | DateRangePeriod


def load_nfse_xml(
    settings: Settings,
    file_path: Path,
    competencia: QueryPeriod,
    *,
    table_name: str = "nfse_xml",
):
    os.environ["DESTINATION__POSTGRES__CREDENTIALS"] = settings.database_url

    resource = nfse_xml_resource(
        file_path,
        competencia,
        table_name=table_name,
    )

    pipeline = dlt.pipeline(
        pipeline_name="iss_fortaleza",
        destination="postgres",
        dataset_name=settings.postgres_schema,
    )
    return pipeline.run(resource)
