from flask import Flask, render_template
import pandas as pd
import plotly.express as px
from plotly.utils import PlotlyJSONEncoder
import json

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

# def create_figure(df):
#     # Use px.line for a line graph. Adjust the column names and the title as per your data's structure and needs.
#     fig = px.line(df, x='timestamp', y='tpm_total', title='TPM over Time')
#     # You can add more customization to the line graph here as needed

#     return fig

# def create_figure(df):
#     # Use px.line for a line graph. Specify multiple columns in the 'y' parameter to plot them on the same graph.
#     # Adjust the column names as per your data's structure and needs.
#     # The 'labels' dictionary is used to provide more descriptive names for each line.
#     fig = px.line(df, x='timestamp', y=['tpm_total', 'tpm_context', 'tpm_gen'],  # Replace 'e2e', 'ttft' with your actual column names
#                   labels={'value': 'Metric Value', 'variable': 'Metrics'},  # Customize label names as needed
#                   title='TPM over Time')

#     # Update line names for clarity
#     fig.for_each_trace(lambda t: t.update(name=t.name.replace('variable=', '')))

#     return fig

def create_figure(df):
    # Ensure the columns are numeric, converting non-numeric values to NaN
    for col in ['tpm_total', 'tpm_context', 'tpm_gen']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Use px.line for a line graph. Specify multiple columns in the 'y' parameter to plot them on the same graph.
    fig = px.line(df, x='timestamp', y=['tpm_total', 'tpm_context', 'tpm_gen'], 
                  labels={'value': 'Metric Value', 'variable': 'Metrics'},  # Customize label names as needed
                  title='Metrics over Time')

    # Update line names for clarity
    fig.for_each_trace(lambda t: t.update(name=t.name.replace('variable=', '')))

    return fig

@app.route('/')
def index():
    df = load_jsonl_data('benchmark_result.jsonl')  # Adjust the filepath if necessary
    fig = create_figure(df)
    graphJSON = json.dumps(fig, cls=PlotlyJSONEncoder)
    return render_template('index.html', graphJSON=graphJSON)

if __name__ == '__main__':
    app.run(debug=True)
