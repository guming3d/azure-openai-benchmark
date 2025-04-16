#!/usr/bin/env python3

import pandas as pd
import argparse
from pathlib import Path
import sys
import io
# Try to import Pillow for image type validation, but make it optional
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

def extract_images_from_parquet(parquet_file_path, output_dir, image_column, image_format='png', filename_prefix='image'):
    """
    Reads a Parquet file, extracts image bytes from a specified column,
    and saves each image to a separate file.

    Args:
        parquet_file_path (str): Path to the input Parquet file.
        output_dir (str): Path to the directory where image files will be saved.
        image_column (str): Name of the column containing image byte data.
        image_format (str): Desired output image format/extension (e.g., 'png', 'jpg').
        filename_prefix (str): Prefix for the output filenames.
    """
    input_path = Path(parquet_file_path)
    output_path = Path(output_dir)
    image_format = image_format.lower().lstrip('.') # Normalize format

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
        print("Input Parquet file is empty. No image files will be created.")
        return

    # --- Validate Image Column ---
    if image_column not in df.columns:
        print(f"Error: Image column '{image_column}' not found in the Parquet file.", file=sys.stderr)
        print(f"Available columns: {list(df.columns)}", file=sys.stderr)
        sys.exit(1)

    # --- Iterate and Write Image Files ---
    num_rows = len(df)
    num_digits = len(str(num_rows - 1))
    file_count = 0
    error_count = 0

    print(f"Extracting images from column '{image_column}' and writing {num_rows} files...")
    for index, row in df.iterrows():
        filename = f"{filename_prefix}_{index:0{num_digits}d}.{image_format}"
        filepath = output_path / filename

        try:
            image_bytes = row[image_column]

            if not isinstance(image_bytes, bytes):
                 # Attempt conversion if possible (e.g., from byte array or dict)
                 try:
                     if isinstance(image_bytes, dict):
                         # Try to extract from a common key like 'bytes'
                         if 'bytes' in image_bytes:
                             print(f"Info: Found dict in row {index}, extracting from 'bytes' key.")
                             image_bytes = image_bytes['bytes']
                             if not isinstance(image_bytes, bytes): # Check if extracted value is bytes
                                 raise TypeError(f"Value under 'bytes' key is not bytes (type: {type(image_bytes)}).")
                         else:
                             # Print the dict structure if 'bytes' key is not found
                             print(f"Warning: Skipping row {index}. Found dict in column '{image_column}' but no 'bytes' key. Dict content: {image_bytes}", file=sys.stderr)
                             error_count += 1
                             continue
                     else:
                        # Try direct conversion for other types
                        image_bytes = bytes(image_bytes)
                 except (TypeError, ValueError, KeyError) as conv_err:
                    print(f"Warning: Skipping row {index}. Data in column '{image_column}' is not bytes or convertible to bytes (type: {type(row[image_column])}). Error: {conv_err}", file=sys.stderr)
                    # Optionally print the problematic data for inspection:
                    # print(f"Data: {row[image_column]}", file=sys.stderr)
                    error_count += 1
                    continue

            if not image_bytes:
                print(f"Warning: Skipping row {index}. Image data in column '{image_column}' is empty.", file=sys.stderr)
                error_count += 1
                continue

            # Optional: Validate image data if Pillow is installed
            if PIL_AVAILABLE:
                try:
                    img = Image.open(io.BytesIO(image_bytes))
                    img.verify() # Verify image data integrity
                    # You could potentially check img.format here against the provided format
                    # but saving with the user-specified extension is generally preferred.
                except Exception as img_err:
                    print(f"Warning: Skipping row {index}. Error validating image data: {img_err}", file=sys.stderr)
                    error_count += 1
                    continue

            # Write the image bytes to the file
            with open(filepath, 'wb') as f:
                f.write(image_bytes)
            file_count += 1

            # Optional: Print progress
            if (file_count % 100 == 0) or (file_count + error_count == num_rows):
                 update_line = f"  ... wrote {file_count}/{num_rows} files"
                 if error_count > 0:
                     update_line += f" ({error_count} errors)"
                 print(update_line, end='')

        except KeyError:
            # Should have been caught earlier, but just in case
            print(f"Error: Column '{image_column}' not found in row {index}. This should not happen.", file=sys.stderr)
            error_count += 1
        except IOError as e:
            print(f"Error writing file '{filepath}': {e}", file=sys.stderr)
            error_count += 1
            # Decide if you want to stop or continue on write error
            # sys.exit(1) # Uncomment to stop on first write error
        except Exception as e:
             print(f"Error processing row {index}: {e}", file=sys.stderr)
             error_count += 1

    # Final status message
    success_message = f"{file_count} image files created in '{output_path.resolve()}'."
    if error_count > 0:
        error_message = f"{error_count} rows encountered errors or were skipped."
        print(f"\nProcessing complete. {success_message} {error_message}")
    else:
        print(f"\nProcessing complete. {success_message}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract images from a specified column in a Parquet file and save them as individual image files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )

    parser.add_argument(
        "parquet_file",
        help="Path to the input Parquet file."
        )
    parser.add_argument(
        "output_dir",
        help="Path to the directory where image files will be saved. Will be created if it doesn't exist."
        )
    parser.add_argument(
        "image_column",
        help="Name of the column containing the image byte data."
        )
    parser.add_argument(
        "--image-format",
        default='png',
        help="Desired output image format (file extension), e.g., 'png', 'jpg', 'webp'."
        )
    parser.add_argument(
        "-p", "--prefix",
        default='image',
        help="Prefix for the output filenames. Files will be named like 'prefix_000.png', 'prefix_001.png', etc."
        )

    args = parser.parse_args()

    if PIL_AVAILABLE:
        print("Pillow (PIL) library found. Image validation enabled.")
    else:
        print("Pillow (PIL) library not found. Image validation disabled. Install with: pip install Pillow")


    extract_images_from_parquet(
        args.parquet_file,
        args.output_dir,
        args.image_column,
        args.image_format,
        args.prefix
    ) 