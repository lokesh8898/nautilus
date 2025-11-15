import argparse
import os
import calendar
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple

import polars as pl


def parse_symbol_and_date_from_filename(csv_path: Path) -> Optional[Tuple[str, str, str, str]]:
    """
    Expect filenames like SYMBOL_DD_MM_YYYY.csv
    Returns (symbol, year, month, day) or None if it doesn't match.
    """
    name = csv_path.stem  # without extension
    parts = name.split("_")
    if len(parts) < 4:
        return None
    symbol = "_".join(parts[:-3])  # in case symbol itself contains underscores
    day, month, year = parts[-3:]
    if not (len(day) == 2 and len(month) == 2 and len(year) == 4 and day.isdigit() and month.isdigit() and year.isdigit()):
        return None
    return symbol, year, month, day


def convert_one_csv(csv_path: Path, out_root: Path, compression: str) -> Optional[Path]:
    parsed = parse_symbol_and_date_from_filename(csv_path)
    if parsed is None:
        return None
    symbol, year, month, day = parsed

    # Read CSV
    df = pl.read_csv(
        csv_path,
        try_parse_dates=False,
        ignore_errors=False,
        infer_schema_length=0,
        low_memory=True,
    )

    # Normalize schema and add datetime
    expected_cols = ["symbol", "date", "time", "open", "high", "low", "close", "volume", "oi"]
    missing = [c for c in expected_cols if c not in df.columns]
    if missing:
        raise ValueError(f"{csv_path} missing columns: {missing}")

    df = df.with_columns(
        [
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            pl.col("volume").cast(pl.Int64),
            pl.col("oi").cast(pl.Int64),
            (
                (pl.col("date") + pl.lit(" ") + pl.col("time"))
                .str.strptime(pl.Datetime, format="%Y-%m-%d %H:%M:%S", strict=False)
                .alias("datetime")
            ),
        ]
    ).with_columns([
        pl.lit(symbol).alias("symbol_root"),
        pl.lit(int(year)).alias("year"),
        pl.lit(int(month)).alias("month"),
        pl.lit(int(day)).alias("day"),
    ])

    # Sort and de-duplicate
    df = df.unique(subset=["datetime", "symbol"], keep="last").sort(["datetime"])  # type: ignore[arg-type]

    # Output path as YYYY/MonthName/DD/SYMBOL/
    month_name = calendar.month_name[int(month)]  # e.g., 04 -> "April"
    partition_dir = out_root / f"{year}" / month_name / f"{day}" / symbol
    partition_dir.mkdir(parents=True, exist_ok=True)

    out_path = partition_dir / f"{csv_path.stem}.parquet"
    df.write_parquet(out_path, compression=compression)
    return out_path


def discover_csvs(in_root: Path) -> list[Path]:
    csvs: list[Path] = []
    for p in in_root.rglob("*.csv"):
        # skip temporary or hidden files just in case
        name = p.name
        if name.startswith("~") or name.startswith("._"):
            continue
        csvs.append(p)
    return csvs


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert nested CSVs to partitioned Parquet")
    parser.add_argument("--input", "-i", type=str, default="daily_symbols_2011", help="Input root directory containing month folders with CSVs")
    parser.add_argument("--output", "-o", type=str, default="parquet_2011", help="Output root directory for Parquet files")
    parser.add_argument("--workers", "-w", type=int, default=os.cpu_count() or 4, help="Number of parallel workers")
    parser.add_argument("--compression", "-c", type=str, default="snappy", choices=["snappy", "zstd", "gzip", "lz4", "uncompressed"], help="Parquet compression codec")
    args = parser.parse_args()

    in_root = Path(args.input).resolve()
    out_root = Path(args.output).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    csv_files = discover_csvs(in_root)
    if not csv_files:
        print(f"No CSV files found under {in_root}")
        return

    print(f"Discovered {len(csv_files)} CSV files. Converting with {args.workers} workers...")

    errors: list[tuple[Path, Exception]] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(convert_one_csv, p, out_root, args.compression): p for p in csv_files}
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                out_path = fut.result()
                completed += 1
                if completed % 500 == 0:
                    print(f"Converted {completed}/{len(csv_files)} ... last: {out_path}")
            except Exception as e:  # noqa: BLE001
                errors.append((p, e))

    print(f"Done. Converted: {completed}, Errors: {len(errors)}. Output root: {out_root}")
    if errors:
        print("Some files failed:")
        for p, e in errors[:50]:
            print(f" - {p}: {e}")
        if len(errors) > 50:
            print(f" ... and {len(errors) - 50} more")


if __name__ == "__main__":
    main()


