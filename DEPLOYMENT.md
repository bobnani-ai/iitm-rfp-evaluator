# Streamlit Community Cloud deployment

The repository can place `Code` at its root or keep it as a subdirectory. In Community Cloud, use **`Code/app.py`** as the entrypoint when this directory is nested. The adjacent **`Code/requirements.txt`** is detected by Community Cloud. No external system packages are needed.

1. Push this project, including `Code/sample_rfps/`, to a GitHub repository you administer. Keep `.streamlit/secrets.toml` and `*.db` out of Git.
2. At [share.streamlit.io](https://share.streamlit.io), select **Create app**, then choose the GitHub repository, branch and `Code/app.py` entrypoint. Select Python 3.12 or 3.13 in advanced settings.
3. To enable live evaluation, users can paste their own key into the left sidebar. Alternatively, add `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `COHERE_API_KEY` or `OPENROUTER_API_KEY` in the app's **Secrets** settings for the corresponding provider. The demo mode works without a key. Do not put keys in the repository or a URL.
4. Deploy and open the assigned `*.streamlit.app` URL. Run the four default sample PDFs in demo mode and download the run JSON. Test one validation case, such as uploading an unreadable or scanned PDF in live mode.
5. Copy the public URL into your submission and capture the screenshots named in `README.md`.

The app seeds SQLite automatically on startup. Community Cloud does not guarantee persistence of local files, including SQLite. Each completed run is stored while the instance remains available; download JSON for a lasting record. A production service needing durable shared history should point the persistence layer to an external database while preserving the same run schema.

Official references: [deployment steps](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [dependency placement](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies), [secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management), [SQLite/local storage](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data).
