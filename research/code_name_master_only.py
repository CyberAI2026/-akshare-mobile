from pathlib import Path

from full_market_data_fetch import fetch_name_tables


if __name__ == "__main__":
    # Kept separate so mapping QA can finish before the full-history artifact.
    output = Path("research_code_name_master")
    output.mkdir(exist_ok=True)
    master = fetch_name_tables(output)
    print(f"CODE_NAME_MASTER_OK rows={len(master)}")
