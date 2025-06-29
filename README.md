iOS Crash Log Analyzer Bot

Project Structure
A brief overview of the key directories:
-   `/database`: Contains all SQLAlchemy models, table creation scripts, and repository patterns for interacting with the PostgreSQL database.
-   `/services`: Holds the core business logic, including the analyzer services for different file types and the integration with the OpenAI API.
-   `/handlers`: Contains all the `aiogram` handlers for processing user commands, messages, and callbacks (e.g., handling `/start`, processing feedback, etc.).
-   `/locales`: Stores localization files for multilingual support (English and Russian) using `GNU Gettext`.


Getting Started

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/W0nderful11/ios.git
    cd ios
    ```

2.  **Set up the virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure your environment:**
    -   Make a copy of the `env-dist` file and name it `.env`.
    -   Open the `.env` file and fill in your Bot Token, Database URL, OpenAI API Key, etc.

5.  **Run the bot:**
    ```bash
    python start.py
    ```