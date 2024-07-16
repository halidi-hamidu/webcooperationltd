FROM odoo:16.0

USER root

COPY ./enterprise-addons /mnt/extra-addons/enterprise-addons
COPY ./custom-addons /mnt/extra-addons/custom-addons

COPY requirements.txt .

RUN pip install -r requirements.txt

USER odoo