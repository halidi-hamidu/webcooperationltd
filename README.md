# Odoo Enterprise Web Application Template

This application provides Odoo enterprise environment

## Prerequisites
- Docker
- Python 3.11+
- Odoo 17.0+

## Development
1. Clone the project to your directory of choosing
2. Startup your app with the following command:
  ```
  docker-compose -f docker-compose.dev.yaml up --force-recreate
  ```

## Deployment
1. Build the application:
```
docker build -t <tagname> .
```
2. Deploy the application:
```
docker-compose -f docker-compose.prod.yaml up --force-recreate
```
