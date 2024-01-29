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

@app.route('/')
def index():
    df = load_jsonl_data('benchmark_result.jsonl')  # Adjust the filepath if necessary
    fig_tpm = create_figure(df, 'timestamp', ['tpm_total', 'tpm_context', 'tpm_gen'], "TPM over Time")
    graphJSON_tpm = json.dumps(fig_tpm, cls=PlotlyJSONEncoder)

    fig_util = create_figure(df, 'timestamp', ['util_avg', 'util_95th'], "Utilization over Time")
    graphJSON_util = json.dumps(fig_util, cls=PlotlyJSONEncoder)

    fig_e2e = create_figure(df, 'timestamp', ['e2e_avg', 'e2e_95th'], "e2e over Time")
    graphJSON_e2e = json.dumps(fig_e2e, cls=PlotlyJSONEncoder)


    return render_template('index.html', graphJSON_tpm=graphJSON_tpm, graphJSON_util=graphJSON_util, graphJSON_e2e = graphJSON_e2e)

if __name__ == '__main__':
    app.run(debug=True)
