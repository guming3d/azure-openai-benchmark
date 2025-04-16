import streamlit as st
import json
import re
import pandas as pd
# Removed Matplotlib imports as we'll use Streamlit native charts
import io
import argparse
import os

# --- Argument Parsing ---
parser = argparse.ArgumentParser(description="Visualize Azure OpenAI benchmark logs.")
parser.add_argument("--log-file", type=str, help="Path to the log file to visualize directly.")
args = parser.parse_args()

# --- Core Data Processing Functions ---
# parse_log_file remains the same as the previous version
def parse_log_file(uploaded_file):
    """
    Parses the uploaded log file content to extract performance metrics
    and test configuration.

    Args:
        uploaded_file: The file object uploaded via Streamlit's file_uploader.

    Returns:
        tuple: A tuple containing:
            - pandas.DataFrame: DataFrame with parsed metrics, or None if parsing fails.
            - dict: Dictionary with test configuration, or None if not found.
    """
    data = []
    config_data = None
    log_pattern = re.compile(r"INFO\s+({.*?})$") # Regex to find JSON in log lines
    config_pattern = re.compile(r"INFO\s+Load test args:\s+({.*?})$") # Regex for config line

    if uploaded_file is None:
        return None, None

    try:
        # Read the file content as a string
        # Handle both Streamlit UploadedFile and file-like object from argparse
        if hasattr(uploaded_file, 'getvalue'): # Streamlit UploadedFile
            file_content = uploaded_file.getvalue().decode("utf-8")
        elif hasattr(uploaded_file, 'read'): # File object from open()
            file_content = uploaded_file.read()
            # Reset cursor for subsequent metric parsing if reading from file object
            if hasattr(uploaded_file, 'seek'):
                uploaded_file.seek(0)
        else:
            st.error("Invalid file object provided.")
            return None, None

        stringio = io.StringIO(file_content)
        lines = stringio.readlines()

        # Find config in the first few lines (adjust limit if needed)
        for line in lines[:10]: # Check first 10 lines for config
             config_match = config_pattern.search(line)
             if config_match:
                 try:
                     config_data = json.loads(config_match.group(1))
                     break # Found config, stop searching
                 except json.JSONDecodeError as e:
                     st.warning(f"Could not parse config JSON: {e} - Line: {line.strip()}", icon="⚠️")
                 except Exception as e: # Catch other potential errors during config parsing
                     st.warning(f"Error processing config line: {e} - Line: {line.strip()}", icon="⚠️")


        for line in lines:
            match = log_pattern.search(line)
            if match:
                json_str = match.group(1)
                # Avoid parsing the config line again as a metric line
                if "Load test args:" not in line:
                    try:
                        log_entry = json.loads(json_str)
                        data.append(log_entry)
                    except json.JSONDecodeError as e:
                        st.warning(f"Skipping metric line due to JSON decode error: {e} - Line: {line.strip()}", icon="⚠️")
                    except Exception as e:
                        st.warning(f"Skipping metric line due to other error: {e} - Line: {line.strip()}", icon="⚠️")

        if not data and config_data is None:
            st.error("No valid metric data or configuration found in the log file.")
            return None, None
        elif not data:
             st.warning("No valid metric data found, but configuration was extracted.", icon="ℹ️")


        df = pd.DataFrame(data) if data else pd.DataFrame() # Handle case where only config is found
        return df, config_data

    except Exception as e:
        st.error(f"An error occurred while reading or parsing the file: {e}")
        return None, None

# preprocess_data remains the same as the previous version
def preprocess_data(df):
    """
    Preprocesses the DataFrame by converting data types and handling missing values.

    Args:
        df (pandas.DataFrame): The DataFrame with raw log data.

    Returns:
        pandas.DataFrame: The preprocessed DataFrame.
    """
    if df is None:
        return None

    if 'timestamp' not in df.columns:
        st.error("Log file missing required 'timestamp' field in JSON data.")
        return None
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')

    # --- Extract nested metrics ---
    df['tpm_total'] = df['tpm'].apply(lambda x: x.get('total', None) if isinstance(x, dict) else None) if 'tpm' in df else None
    df['tpm_context_text'] = df['tpm'].apply(lambda x: x.get('context_text', None) if isinstance(x, dict) else None) if 'tpm' in df else None
    df['tpm_context_image'] = df['tpm'].apply(lambda x: x.get('context_image', None) if isinstance(x, dict) else None) if 'tpm' in df else None
    df['tpm_gen'] = df['tpm'].apply(lambda x: x.get('gen', None) if isinstance(x, dict) else None) if 'tpm' in df else None

    df['e2e_avg'] = df['e2e'].apply(lambda x: x.get('avg', None) if isinstance(x, dict) else None) if 'e2e' in df else None
    df['e2e_95th'] = df['e2e'].apply(lambda x: x.get('95th', None) if isinstance(x, dict) else None) if 'e2e' in df else None

    df['ttft_avg'] = df['ttft'].apply(lambda x: x.get('avg', None) if isinstance(x, dict) else None) if 'ttft' in df else None
    df['ttft_95th'] = df['ttft'].apply(lambda x: x.get('95th', None) if isinstance(x, dict) else None) if 'ttft' in df else None

    df['tbt_avg'] = df['tbt'].apply(lambda x: x.get('avg', None) if isinstance(x, dict) else None) if 'tbt' in df else None
    df['tbt_95th'] = df['tbt'].apply(lambda x: x.get('95th', None) if isinstance(x, dict) else None) if 'tbt' in df else None

    df['context_tpr_avg'] = df['context_tpr_avg'] if 'context_tpr_avg' in df else None

    # --- Convert columns to numeric ---
    # Use None for missing values, then convert. 'coerce' turns errors into NaT/NaN.
    numeric_cols = [
        'run_seconds', 'rpm', 'processing', 'completed', 'failures', 'throttled',
        'requests', 'tpm_total', 'tpm_context_text', 'tpm_context_image', 'tpm_gen',
        'e2e_avg', 'e2e_95th', 'ttft_avg', 'ttft_95th', 'tbt_avg', 'tbt_95th',
        'context_tpr_avg'
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Drop rows where timestamp is NaT
    df.dropna(subset=['timestamp'], inplace=True)

    # Set timestamp as index - crucial for Streamlit charts
    if not df.empty:
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True) # Sort by the new index

    # Drop original nested dictionary columns
    cols_to_drop = ['tpm', 'e2e', 'ttft', 'tbt', 'gen_tpr', 'util']
    existing_cols_to_drop = [col for col in cols_to_drop if col in df.columns]
    if existing_cols_to_drop:
        df.drop(columns=existing_cols_to_drop, errors='ignore', inplace=True)

    return df

# Removed the Matplotlib plot_metrics function

# --- Streamlit App ---

st.set_page_config(layout="wide")
st.title("Azure OpenAI performance data visualization")

st.markdown("""
Upload your benchmark log file (containing JSON metrics per line) to visualize the performance.
The script expects log lines with `INFO` level containing a JSON payload with metrics like `timestamp`, `rpm`, `tpm`, `e2e`, etc.
Or provide the path using the `--log-file` command-line argument.
""")

log_file_to_process = None
uploaded_file_name = None

# Check if log file path is provided via argument
if args.log_file:
    if os.path.exists(args.log_file):
        try:
            # Open the file in text mode directly
            log_file_to_process = open(args.log_file, 'r', encoding='utf-8')
            uploaded_file_name = args.log_file
            st.info(f"Processing log file from command line argument: {args.log_file}")
        except Exception as e:
            st.error(f"Error opening log file {args.log_file}: {e}")
            log_file_to_process = None # Ensure it's None if opening failed
    else:
        st.error(f"Log file not found at path: {args.log_file}")

# If no command-line argument or error opening, use the uploader
if log_file_to_process is None:
    uploaded_file = st.file_uploader("Choose a log file (.txt, .log)", type=['txt', 'log'])
    if uploaded_file is not None:
        log_file_to_process = uploaded_file
        uploaded_file_name = uploaded_file.name
else:
    # Hide the uploader if we are processing from args
    st.empty() # Creates a placeholder that we don't fill

# Process the file (either from argument or uploader)
if log_file_to_process is not None:
    if uploaded_file_name: # Display success only if a file name is available
        st.success(f"Processing '{uploaded_file_name}'...")

    with st.spinner('Parsing and processing log file...'):
        raw_df, config_data = parse_log_file(log_file_to_process) # Capture config_data
        processed_df = preprocess_data(raw_df)
        # Close the file if opened via argparse
        if hasattr(log_file_to_process, 'close') and log_file_to_process is not uploaded_file:
             log_file_to_process.close()

    # --- Display Configuration ---
    if config_data:
        st.subheader("Test Configuration")
        # Convert dict to DataFrame for better display
        config_df = pd.DataFrame(list(config_data.items()), columns=['Parameter', 'Value'])
        st.table(config_df.set_index('Parameter')) # Use st.table for static display
    elif not raw_df.empty: # Show message only if we expected config but didn't find it
         st.warning("Could not find test configuration information in the log file.", icon="⚠️")

    if processed_df is not None and not processed_df.empty:
        st.subheader("Performance Plots")
        st.markdown("Hover over the charts to see details.")

        # Create columns for layout (optional, but can help organize)
        col1, col2 = st.columns(2)

        with col1:
            # --- RPM Chart ---
            st.subheader("Requests Per Minute (RPM)")
            rpm_cols = ['rpm']
            if all(col in processed_df.columns for col in rpm_cols):
                st.line_chart(processed_df[rpm_cols].dropna())
            else:
                st.caption("RPM data not available.")

            # --- E2E Latency Chart ---
            st.subheader("End-to-End (E2E) Latency (s)")
            e2e_cols = ['e2e_avg', 'e2e_95th']
            if any(col in processed_df.columns for col in e2e_cols): # Plot if at least one column exists
                cols_to_plot = [col for col in e2e_cols if col in processed_df.columns]
                st.line_chart(processed_df[cols_to_plot].dropna(how='all'))
            else:
                st.caption("E2E Latency data not available.")

            # --- TBT Latency Chart ---
            st.subheader("Time Between Tokens (TBT) Latency (s)")
            tbt_cols = ['tbt_avg', 'tbt_95th']
            if any(col in processed_df.columns for col in tbt_cols):
                cols_to_plot = [col for col in tbt_cols if col in processed_df.columns]
                st.line_chart(processed_df[cols_to_plot].dropna(how='all'))
            else:
                st.caption("TBT Latency data not available.")

            # --- Processing/Throttled Chart ---
            st.subheader("Processing and Throttled Requests")
            proc_cols = ['processing', 'throttled']
            if any(col in processed_df.columns for col in proc_cols):
                cols_to_plot = [col for col in proc_cols if col in processed_df.columns]
                st.line_chart(processed_df[cols_to_plot].dropna(how='all'))
            else:
                st.caption("Processing/Throttled data not available.")


        with col2:
            # --- TPM Chart ---
            st.subheader("Tokens Per Minute (TPM)")
            tpm_cols = ['tpm_total', 'tpm_gen', 'tpm_context_text', 'tpm_context_image']
            # Check which TPM columns actually exist in the DataFrame
            existing_tpm_cols = [col for col in tpm_cols if col in processed_df.columns]
            if existing_tpm_cols:
                 # Fill NaN with 0 specifically for plotting TPM components that might be sparse
                st.line_chart(processed_df[existing_tpm_cols].fillna(0))
            else:
                st.caption("TPM data not available.")

            # --- TTFT Latency Chart ---
            st.subheader("Time To First Token (TTFT) Latency (s)")
            ttft_cols = ['ttft_avg', 'ttft_95th']
            if any(col in processed_df.columns for col in ttft_cols):
                cols_to_plot = [col for col in ttft_cols if col in processed_df.columns]
                st.line_chart(processed_df[cols_to_plot].dropna(how='all'))
            else:
                st.caption("TTFT Latency data not available.")

            # --- Failures/Completed Chart ---
            st.subheader("Failures and Completed Requests")
            fail_cols = ['failures', 'completed']
            if any(col in processed_df.columns for col in fail_cols):
                cols_to_plot = [col for col in fail_cols if col in processed_df.columns]
                st.line_chart(processed_df[cols_to_plot].dropna(how='all'))
            else:
                st.caption("Failures/Completed data not available.")

        st.success("Plots generated!")

    elif raw_df is not None:
         st.error("Could not preprocess data. Check log file format and content.")
    # else: Error message handled in parse_log_file

elif not args.log_file: # Only show 'Please upload' if not using args
    st.info("Please upload a log file or provide `--log-file` argument to begin.")

st.markdown("---")
st.caption("App powered by Streamlit.")
