#!/usr/bin/env python3

import pandas as pd
import argparse
from pathlib import Path
import sys

def convert_parquet_to_text_files(parquet_file_path, output_dir, format_type='keyvalue', filename_prefix='row'):
    """
    Reads a Parquet file and writes each row to a separate text file.

    Args:
        parquet_file_path (str): Path to the input Parquet file.
        output_dir (str): Path to the directory where text files will be saved.
        format_type (str): Output format ('keyvalue', 'csv', 'json').
        filename_prefix (str): Prefix for the output filenames.
    """
    input_path = Path(parquet_file_path)
    output_path = Path(output_dir)

    # --- Input Validation ---
    if not input_path.is_file():
        print(f"Error: Input Parquet file not found at '{input_path}'", file=sys.stderr)
        sys.exit(1)
    if not input_path.suffix.lower() == '.parquet':
        print(f"Warning: Input file '{input_path.name}' might not be a Parquet file (expected .parquet extension).", file=sys.stderr)

    # --- Create Output Directory ---
    try:
        output_path.mkdir(parents=True, exist_ok=True)
        print(f"Output directory: '{output_path.resolve()}'")
    except OSError as e:
        print(f"Error: Could not create output directory '{output_path}': {e}", file=sys.stderr)
        sys.exit(1)

    # --- Read Parquet File ---
    try:
        print(f"Reading Parquet file: '{input_path}'...")
        # Consider using chunking for very large files if memory becomes an issue
        # For this task (iterating row by row), reading the whole DataFrame is often fine.
        df = pd.read_parquet(input_path)
        print(f"Successfully read {len(df)} rows.")
    except ImportError:
         print("Error: Missing Parquet engine. Please install 'pyarrow' or 'fastparquet'.", file=sys.stderr)
         print("Suggestion: pip install pyarrow", file=sys.stderr)
         sys.exit(1)
    except Exception as e:
        print(f"Error reading Parquet file '{input_path}': {e}", file=sys.stderr)
        sys.exit(1)

    if df.empty:
        print("Input Parquet file is empty. No text files will be created.")
        return

    # --- Iterate and Write Files ---
    num_rows = len(df)
    # Determine padding width for filenames based on the number of rows for nice sorting
    num_digits = len(str(num_rows - 1))
    file_count = 0

    print(f"Writing {num_rows} text files...")
    for index, row in df.iterrows():
        # Generate filename (e.g., row_000.txt, row_001.txt, ...)
        filename = f"{filename_prefix}_{index:0{num_digits}d}.txt"
        filepath = output_path / filename

        # Format row data based on the chosen format
        try:
            content_string = ""
            if format_type == 'keyvalue':
                lines = []
                for col_name, value in row.items():
                    # Ensure value is string, handle None
                    value_str = str(value) if value is not None else 'None'
                    lines.append(f"{col_name}: {value_str}")
                content_string = "\n".join(lines)
            elif format_type == 'csv':
                # Simple CSV - does not handle quotes or commas within values well.
                # For more robust CSV, consider using the csv module per row.
                content_string = ",".join(str(value) if value is not None else '' for value in row.values)
            elif format_type == 'json':
                # Convert row to a dictionary and then to a JSON string
                import json # Import only if needed
                content_string = json.dumps(row.to_dict())
            else:
                # Should not happen due to argparse choices, but good practice
                print(f"Error: Invalid format type '{format_type}' encountered.", file=sys.stderr)
                continue # Skip this row

            # Write the formatted string to the text file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content_string)
            file_count += 1

            # Optional: Print progress
            if (file_count % 1000 == 0) or (file_count == num_rows):
                 print(f"  ... wrote {file_count}/{num_rows} files", end='\r')


        except IOError as e:
            print(f"\nError writing file '{filepath}': {e}", file=sys.stderr)
            # Decide if you want to stop or continue on write error
            # sys.exit(1) # Uncomment to stop on first write error
        except Exception as e:
             print(f"\nError processing row {index}: {e}", file=sys.stderr)
             # Decide if you want to stop or continue on processing error

    print(f"\nProcessing complete. {file_count} text files created in '{output_path.resolve()}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert each row of a Parquet file into a separate text file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter # Show default values in help
        )

    parser.add_argument(
        "parquet_file",
        help="Path to the input Parquet file."
        )
    parser.add_argument(
        "output_dir",
        help="Path to the directory where text files will be saved. Will be created if it doesn't exist."
        )
    parser.add_argument(
        "-f", "--format",
        choices=['keyvalue', 'csv', 'json'],
        default='keyvalue',
        help="Output format for each text file."
             " 'keyvalue': One 'column_name: value' pair per line."
             " 'csv': Comma-separated values (simple)."
             " 'json': Row represented as a JSON object."
        )
    parser.add_argument(
        "-p", "--prefix",
        default='row',
        help="Prefix for the output filenames. Files will be named like 'prefix_000.txt', 'prefix_001.txt', etc."
        )

    args = parser.parse_args()

    convert_parquet_to_text_files(args.parquet_file, args.output_dir, args.format, args.prefix)