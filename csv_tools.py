import pandas as pd
import os

CSV_PATH = "collaborators.csv"

# Helper function to ensure the CSV exists with correct headers
def _ensure_csv_exists_with_headers():
    if not os.path.exists(CSV_PATH):
        # Create an empty DataFrame with specified columns
        empty_df = pd.DataFrame(columns=["name", "email"])
        empty_df.to_csv(CSV_PATH, index=False)
    else:
        # Check if the existing CSV has the correct headers
        try:
            df = pd.read_csv(CSV_PATH)
            if "name" not in df.columns or "email" not in df.columns:
                print(f"Warning: {CSV_PATH} exists but is missing 'name' or 'email' columns. Recreating.")
                empty_df = pd.DataFrame(columns=["name", "email"])
                empty_df.to_csv(CSV_PATH, index=False)
        except pd.errors.EmptyDataError:
            # File exists but is empty, create with headers
            print(f"Warning: {CSV_PATH} is empty. Adding headers.")
            empty_df = pd.DataFrame(columns=["name", "email"])
            empty_df.to_csv(CSV_PATH, index=False)
        except Exception as e:
            print(f"Error checking {CSV_PATH}: {e}. Recreating.")
            empty_df = pd.DataFrame(columns=["name", "email"])
            empty_df.to_csv(CSV_PATH, index=False)


def get_email_from_csv(name: str) -> str:
    """
    Retrieves the email of a collaborator from the CSV file.

    Args:
        name (str): The name of the collaborator.

    Returns:
        str: The email address if found, None otherwise.
    """
    _ensure_csv_exists_with_headers() # Ensure CSV is ready
    df = pd.read_csv(CSV_PATH)
    # Check if df is empty after reading, no point in searching
    if df.empty:
        return None

    row = df[df["name"].str.lower() == name.lower()]
    if not row.empty:
        return row.iloc[0]["email"]
    return None

def add_collaborator(name: str, email: str):
    """
    Adds a new collaborator to the CSV file.

    Args:
        name (str): The name of the collaborator.
        email (str): The email address of the collaborator.

    Returns:
        str: A message indicating whether the collaborator was added or already exists.
    """
    _ensure_csv_exists_with_headers() # Ensure CSV is ready
    df = pd.read_csv(CSV_PATH)

    # Check if name already exists (case-insensitive)
    if not df.empty and name.lower() in df["name"].str.lower().values:
        return f"Collaborator '{name}' already exists."

    new_collaborator = pd.DataFrame([{"name": name, "email": email}])
    df = pd.concat([df, new_collaborator], ignore_index=True)
    df.to_csv(CSV_PATH, index=False)
    return f"Collaborator '{name}' with email '{email}' added."