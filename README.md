# haac — Home Assistant as Code

Terraform-style configuration management for Home Assistant.

## Install

```bash
pip install haac
```

## Usage

```bash
haac init          # scaffold a new project
haac plan          # show what would change
haac apply         # push changes to HA
haac pull          # pull HA state into local files
haac delete kind:id  # remove resources from HA
```
