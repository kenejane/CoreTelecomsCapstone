# Dockerfile

ARG AIRFLOW_VERSION=3.1.0
ARG PYTHON_VERSION=3.12

# Use explicit Python image tag
FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

# IMPORTANT: Run pip as 'airflow' user (default in this image)
USER airflow

# Make project-level modules (e.g. /opt/airflow/include) importable in DAGs
ENV PYTHONPATH="${PYTHONPATH}:/opt/airflow:/opt/airflow/include"

# Copy requirements and install extra Python deps
COPY requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Bundle DAGs and supporting modules into the image for portability
WORKDIR /opt/airflow

RUN mkdir -p /opt/airflow/dags /opt/airflow/include

COPY dags/ /opt/airflow/dags/
COPY include/ /opt/airflow/include/
