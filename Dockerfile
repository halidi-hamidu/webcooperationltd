FROM odoo:19.0-20260409

USER root

RUN apt update -y && apt install -y build-essential libssl-dev libffi-dev python3-dev cargo python3-venv

COPY requirements.txt .
RUN rm -f /usr/lib/python*/EXTERNALLY-MANAGED
RUN pip install -r requirements.txt --ignore-installed urllib3

COPY ./enterprise-addons /mnt/extra-addons/enterprise-addons
COPY ./custom-addons /mnt/extra-addons/custom-addons

USER odoo
