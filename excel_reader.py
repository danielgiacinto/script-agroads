from pathlib import Path

import pandas as pd


def read_products(excel_path: Path) -> list[dict]:
    df = pd.read_excel(excel_path, header=0)
    df = df.dropna(how="all")
    df = df.fillna("")
    products = []
    for _, row in df.iterrows():
        product = {str(k).strip(): _serialize(v) for k, v in row.items()}
        products.append(product)
    return products


def _serialize(val) -> str | int | float:
    if pd.isna(val):
        return ""
    if isinstance(val, (int, float)) and val == int(val):
        return int(val)
    return str(val).strip()
