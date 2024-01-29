from flask import Flask, render_template
import pandas as pd
import plotly.express as px
from plotly.utils import PlotlyJSONEncoder
import json
from datetime import datetime

app = Flask(__name__,  template_folder='templates')

def load_jsonl_data(filepath):
    data = []
    with open(filepath, 'r') as file:
        for line in file:
            # Load each line as a JSON object
            json_obj = json.loads(line)
            
            # Flatten the JSON object, specifying the path to the embedded fields
            # Adjust the path according to the actual structure of your JSONL file
            flattened_obj = pd.json_normalize(json_obj, sep='_')
            data.append(flattened_obj)
    
    # Concatenate all the flattened data frames
    df = pd.concat(data, ignore_index=True)
    return df


def create_figure(df, x_column, y_columns, title):
    # Ensure the specified columns are numeric, converting non-numeric values to NaN
    for col in y_columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Use Plotly Express to create the figure
    fig = px.line(df, x=x_column, y=y_columns,
                  labels={'value': 'Metric Value', 'variable': 'Metrics'},  # Customize label names as needed
                  title=title)

    # Update line names for clarity
    fig.for_each_trace(lambda t: t.update(name=t.name.replace('variable=', '')))

    return fig

def create_figure_util(df, x_column, y_columns, title):
    for col in y_columns:
        # Check if the column contains percentage values
        if df[col].dtype == 'object' and df[col].str.contains('%').any():
            # Convert percentage strings to float, handling 'n/a' and other non-convertible strings
            df[col] = df[col].str.rstrip('%').apply(lambda x: pd.to_numeric(x, errors='coerce')) / 100.0
        else:
            # Convert column to numeric, coercing errors to NaN
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Use Plotly Express to create the figure
    fig = px.line(df, x=x_column, y=y_columns,
                  labels={'value': 'Metric Value', 'variable': 'Metrics'},  # Customize label names as needed
                  title=title)

    # Update line names for clarity
    fig.for_each_trace(lambda t: t.update(name=t.name.replace('variable=', '')))

    # Set y-axis range to have a maximum of 100 (assuming it's percentage)
    fig.update_layout(yaxis_range=[0, 1])  # yaxis_range is [min, max], setting max to 1 since the data is now in decimal form

    return fig

def get_current_time_formatted():
    now = datetime.now()
    formatted_time = now.strftime("%Y-%m-%d-%H-%M")
    return formatted_time

@app.route('/')
def index():
    df = load_jsonl_data('benchmark_result.jsonl')  # Adjust the filepath if necessary
    fig_tpm = create_figure(df, 'timestamp', ['tpm_total', 'tpm_context', 'tpm_gen'], "TPM over Time")
    graphJSON_tpm = json.dumps(fig_tpm, cls=PlotlyJSONEncoder)

    fig_util = create_figure_util(df, 'timestamp', ['util_avg', 'util_95th'], "Utilization over Time")
    graphJSON_util = json.dumps(fig_util, cls=PlotlyJSONEncoder)

    fig_e2e = create_figure(df, 'timestamp', ['e2e_avg', 'e2e_95th'], "e2e over Time")
    graphJSON_e2e = json.dumps(fig_e2e, cls=PlotlyJSONEncoder)


    current_time = get_current_time_formatted()

    return render_template('index.html', graphJSON_tpm=graphJSON_tpm, graphJSON_util=graphJSON_util, graphJSON_e2e = graphJSON_e2e, formatted_time = current_time)

if __name__ == '__main__':
    app.run(debug=True)
