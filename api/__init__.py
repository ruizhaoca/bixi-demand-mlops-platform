"""FastAPI prediction service for the BIXI demand models.

This is the third serving tier (alongside the two Streamlit deployments): a thin
REST API over the existing model bundles in ``src/bixi``. It adds **no** ML logic
— it only wires the committed/​S3 artifacts to typed HTTP endpoints.
"""
