FROM quay.io/astronomer/astro-runtime:13.0.0

USER root
WORKDIR /usr/local/airflow

COPY requirements.txt pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps --editable .

COPY dags ./dags
COPY include ./include
COPY plugins ./plugins

RUN mkdir -p /usr/local/airflow/data/nfse \
        /usr/local/airflow/data/artifacts \
    && chown -R astro:0 /usr/local/airflow

USER astro
