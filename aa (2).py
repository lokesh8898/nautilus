import pandas as pd
from pathlib import Path
import re

# Directory containing CSV files
csv_directory = r"C:\Users\User\Downloads\Telegram Desktop"

# Get all CSV files in the directory
csv_files = list(Path(csv_directory).glob("*.csv"))

# Sort files in a deterministic, human (natural) order so output order matches input order
def _natural_key(path: Path):
    def _key(s: str):
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]
    return _key(path.name)

csv_files.sort(key=_natural_key)

# Output directory for parquet files
output_dir = Path(csv_directory) / "parquet output"
output_dir.mkdir(parents=True, exist_ok=True)

print(f"Found {len(csv_files)} CSV file(s) to convert in sequential order...\n")

# Counter for successful conversions
converted_count = 0
failed_count = 0

# Manifest to record input/output order mapping
manifest_rows = []

# Process each CSV file sequentially (already sequential in this loop)
for idx, csv_file in enumerate(csv_files, start=1):
    try:
        # Output parquet file in separate folder with numeric prefix to preserve order
        parquet_file = output_dir / f"{idx:04d}_{csv_file.stem}.parquet"
        
        # Read CSV
        print(f"Reading: {csv_file.name}...")
        df = pd.read_csv(csv_file)
        
        # Write to parquet
        df.to_parquet(parquet_file, index=False)
        
        print(f"✅ [{idx:04d}] Converted: {csv_file.name} -> {parquet_file.name}\n")
        converted_count += 1
        manifest_rows.append((idx, csv_file.name, parquet_file.name))
        
    except Exception as e:
        print(f"❌ Failed to convert {csv_file.name}: {str(e)}\n")
        failed_count += 1

# Write manifest CSV mapping to preserve the processing order
try:
    import csv as _csv
    manifest_path = output_dir / "conversion_order.csv"
    with manifest_path.open(mode="w", newline="", encoding="utf-8") as f:
        writer = _csv.writer(f)
        writer.writerow(["order", "input_csv", "output_parquet"])
        for row in manifest_rows:
            writer.writerow(row)
    print(f"Manifest written: {manifest_path}")
except Exception as e:
    print(f"Warning: failed to write manifest: {e}")

# Summary
print("=" * 60)
print(f"Conversion Summary:")
print(f"  ✅ Successfully converted: {converted_count}")
print(f"  ❌ Failed: {failed_count}")
print(f"  📊 Total processed: {len(csv_files)}")
print("=" * 60)
