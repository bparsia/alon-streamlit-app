# ALOn Model Explorer - Streamlit App

Interactive web application for editing, visualizing, and reasoning over ALOn models.

## Features

- **Model Definition**: Edit Mermaid diagrams with live preview
- **Complete Model**: View generated complete model with all histories
- **Responsibility Analysis**: Run full responsibility analysis with Konclude
- **Model Repository**: Load example models or upload your own

## Installation

Streamlit is included in the main requirements.txt. From the repository root:

```bash
pip install -r requirements.txt
```

## Running Locally

From the `alon_experiments` directory:

```bash
streamlit run streamlit_app/app.py
```

Or from the `streamlit_app` directory:

```bash
streamlit run app.py
```

The app will open in your browser at http://localhost:8501

## Usage

### 1. Model Definition

The first section shows a Mermaid text editor on the left and a preview of your partial diagram on the right.

- Edit the Mermaid diagram text
- Click "🔄 Refresh Preview" to update the preview
- Use YAML frontmatter to specify actions, opposings, aliases, etc.

### 2. Complete Model

The second section shows:
- Model overview (agents, actions, opposings, histories)
- Complete Index structure diagram (all generated histories)

### 3. Responsibility Analysis

The third section allows you to:
- Run full responsibility analysis with all operators (PRES, SRES, RES, DXSTIT, BUT, NESS)
- View results in a formatted table

## Model Repository

Use the sidebar to:
- Load example models from `models/` directory
- Upload your own .mmd files
- Submit new models to the community (coming soon)

## Deployment

### Streamlit Community Cloud

To deploy to Streamlit Community Cloud:

1. Push this repository to GitHub
2. Go to https://share.streamlit.io
3. Connect your GitHub account
4. Select this repository and specify `streamlit_app/app.py` as the main file

### Konclude Setup

The app requires Konclude reasoner. For deployment:

- Create `packages.txt` in `streamlit_app/` directory with:
  ```
  konclude
  ```
- Ensure `reasoner_config.toml` points to the correct Konclude path

## Example Models

Example models are stored in `streamlit_app/models/`:

- `3.1_partial.mmd` - Alice and Beth shooting scenario

## Technical Notes

- Uses DBT (Deontic Branching Time) Mermaid format as primary input
- Automatically generates all complete histories based on agent actions
- Opposing relations do NOT filter histories (used only in semantics)
- Temporal depth = 1 (single choice point per history)
