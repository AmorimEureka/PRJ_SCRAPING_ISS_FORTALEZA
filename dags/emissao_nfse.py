from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.decorators import dag, task
from airflow.exceptions import AirflowException
from airflow.operators.python import get_current_context
from airflow.providers.postgres.hooks.postgres import PostgresHook

from nfs_fortaleza.batch import (
    BatchIssuanceService,
    BatchPayload,
    PostgresIssuanceRepository,
)
from nfs_fortaleza.config import load_settings
from nfs_fortaleza.issuance import ISSUER_CNPJ, NfseIssuanceClient
from nfs_fortaleza.portal import PortalOptions


POSTGRES_CONN_ID = os.getenv(
    "NFSE_POSTGRES_CONN_ID",
    "postgres_prontocardio",
)
POSTGRES_SCHEMA = os.getenv("POSTGRES_SCHEMA", "api_prontocardio")
DOWNLOADS_DIR = Path(
    os.getenv("NFSE_DOWNLOADS_DIR", "/usr/local/airflow/data/nfse")
)
ARTIFACTS_DIR = Path(
    os.getenv("NFSE_ARTIFACTS_DIR", "/usr/local/airflow/data/artifacts")
)


@dag(
    dag_id="emissao_nfse",
    description="Emite somente solicitacoes de NFS-e aprovadas e pendentes.",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="America/Fortaleza"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "airflow",
        "depends_on_past": False,
        "retries": 0,
        "execution_timeout": timedelta(hours=4),
    },
    tags=["nfse", "emissao"],
)
def emissao_nfse():
    @task(task_id="processar_lote", pool="nfse_portal")
    def processar_lote() -> dict[str, object]:
        context = get_current_context()
        dag_run = context["dag_run"]
        payload = BatchPayload.from_mapping(dag_run.conf)
        dag_run_id = str(dag_run.run_id)

        hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        os.environ.setdefault("DATABASE_URL", hook.get_uri())
        os.environ.setdefault("POSTGRES_SCHEMA", POSTGRES_SCHEMA)
        settings = load_settings()
        options = PortalOptions(
            downloads_dir=DOWNLOADS_DIR,
            artifacts_dir=ARTIFACTS_DIR,
        )

        connection = hook.get_conn()
        try:
            repository = PostgresIssuanceRepository(
                connection,
                schema=settings.postgres_schema,
            )
            issuer = NfseIssuanceClient(settings, options)
            service = BatchIssuanceService(
                repository,
                issuer,
                cnpj=os.getenv("NFSE_ISSUER_CNPJ", ISSUER_CNPJ),
                default_city=os.getenv("NFSE_DEFAULT_CITY", "FORTALEZA"),
                default_uf=os.getenv("NFSE_DEFAULT_UF", "CE"),
            )
            summary = service.run(payload, dag_run_id=dag_run_id)
        finally:
            connection.close()

        if summary.incomplete:
            raise AirflowException(
                "Lote de NFS-e concluido com pendencias ou erros: "
                f"{summary.as_dict()}"
            )
        return summary.as_dict()

    processar_lote()


dag = emissao_nfse()
