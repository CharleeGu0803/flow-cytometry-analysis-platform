# Flow Cytometry Analysis Platform

A Flask web app for uploading flow cytometry (`.fcs`) files, exploring them as density plots, and counting cells inside gates.

## Origin

This project started as a team project in the ANU TechLauncher program (started 2024), built with a team of students. This repository is my own maintained version. I restructured the codebase, fixed security issues and bugs, and removed all research data and project-management material from the original repo.

## Features

- User accounts with registration, login and an admin role
- Datasets → batches → FCS files hierarchy, scoped per user
- Upload FCS files into a batch
- Density scatter plots for any pair of channels, on linear, logicle or arcsinh scales, with box zoom
- Cell counts (and % of total) inside a rectangle or polygon drawn on the plot, or one of the panel's predefined gates
- Per-batch PDF report of the cell count for every gate in every file
- Admin page to list users, reset passwords and delete accounts

## Tech stack

Python 3.10+, Flask, Flask-SQLAlchemy (SQLite), [FlowKit](https://github.com/whitews/FlowKit) / FlowUtils, matplotlib, SciPy, ReportLab.

## Getting started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env          # then set FLASK_SECRET_KEY
flask create-admin admin      # prompts for a password
flask run
```

Open http://127.0.0.1:5000, register an account (or log in as the admin), create a dataset and a batch, and upload `.fcs` files from **Upload Files**.

The SQLite database, uploaded files and generated plots are stored under `data/`, which is git-ignored. Set `FLOW_DATA_DIR` to store them somewhere else.

## Panel configuration

[`flowplatform/default_config.json`](flowplatform/default_config.json) defines the antibody panel:

- `channels`: display name (`ch_name`) → detector name in the FCS file (`fluoro_name`)
- `gates`: polygon gates on a channel pair. Coordinates on scatter channels (FSC/SSC) are raw linear values. Coordinates on fluorescence channels are logicle values × 262144.

To use a different panel, set `FLOW_PANEL_CONFIG` to point at your own JSON file.

## Project layout

```
flowplatform/
  __init__.py        app factory and the `flask create-admin` command
  config.py          settings, read from environment variables
  models.py          User / Dataset / Batch / File
  auth.py            session-based login_required / admin_required
  views.py           pages and JSON API
  admin.py           admin pages and API
  analysis.py        FCS loading, gating, plotting
  reports.py         PDF batch report
  templates/
tests/
```

## Tests

```bash
pytest
```
