
import pandas as pd
import argparse
from typing import List
from flask import render_template, request
import connexion
from log_analysis import get_dataframe, get_durations
from glob import glob

from structuredlog import calculate_p95, process, LogEntry, LogType
from aspenlog import process_aspenlog, AspenLogEntry
from exception_entry import ExceptionEntry, get_exceptions
from tool_entry import ToolEntry, get_tools_and_mark_log_entries_with_concurrent_jobs, ToolEntryType, ToolLocationType

# app = Flask(__name__)
app = connexion.App(__name__, specification_dir="./")

log_entries : List[LogEntry] = []
aspen_log_entries : List[AspenLogEntry] = []
exceptions_sorted : List[ExceptionEntry] = []
tool_entries : List[ToolEntry] = []
durations : dict = {}
df = None

@app.route('/')
def route_index():
    context = {
        "exception_sum": sum([len(exception.log_entries) for exception in exceptions_sorted]),
        "p95": calculate_p95(log_entries),
        "tools_aborted": sum(1 for aspen_log_entry in aspen_log_entries if 'Abort Tool Job' in aspen_log_entry.message),
        "started_len": sum(1 for tool in tool_entries if tool.type == ToolEntryType.START ),
        "finished_len": sum(1 for tool in tool_entries if tool.type == ToolEntryType.FINISH ),
        "report_local_deliberate": sum(1 for tool in tool_entries if tool.type == ToolEntryType.START and tool.location == ToolLocationType.LOCAL_DELIBERATE.name ),
        "report_local_unserializable": sum(1 for tool in tool_entries if tool.type == ToolEntryType.START and tool.location == ToolLocationType.LOCAL_UNSERIALIZABLE.name ),
        "report_remote": sum(1 for tool in tool_entries if tool.type == ToolEntryType.START and tool.location == ToolLocationType.REMOTE.name ),
    }

    print("abort", context["tools_aborted"])

    return render_template("index.html", **context)

@app.route('/exceptions')
def route_exceptions():
    global exceptions_sorted
    return render_template("exceptions.html", exceptions_sorted=exceptions_sorted)

@app.route('/exception-entry/<entry_index>')
def route_exception_entry(entry_index):
    global exceptions_sorted
    return render_template("exception-entry.html", exception=exceptions_sorted[int(entry_index)])

@app.route('/thread-logs/<thread_id>')
def route_thread_logs(thread_id):
    global exceptions_sorted
    thread_log_entries = [entry for entry in log_entries if entry.thread == thread_id]
    return render_template("log-entries.html", log_entries=thread_log_entries, log_filter_id=thread_id, log_type='Thread')

@app.route('/session-logs/<session_id>')
def route_session_logs(session_id):
    global log_entries
    session_log_entries = [entry for entry in log_entries if (entry.type == LogType.RESPONSE or entry.type == LogType.REQUEST) and entry.sessionid == session_id]
    return render_template("log-entries.html", log_entries=session_log_entries, log_filter_id=session_id, log_type='Session')

@app.route('/logs')
def route_logs():
    global log_entries
    return render_template("log-entries.html", log_entries=log_entries, log_filter_id='', log_type='Logs')

@app.route('/aspenlogs')
def route_aspen_logs():
    global aspen_log_entries
    print(len(aspen_log_entries))
    return render_template("aspen-log-entries.html", log_entries=aspen_log_entries, log_filter_id='', log_type='Aspen Logs')

@app.route('/tools')
def route_tools():
    started_len = sum(1 for tool in tool_entries if tool.type == ToolEntryType.START )
    finished_len = sum(1 for tool in tool_entries if tool.type == ToolEntryType.FINISH )
    return render_template("tool-entries.html", tool_entries=tool_entries, started_len=started_len, finished_len=finished_len )

# makes a link to requests path, filtered to paths that match val
def make_requests_link(val):
    print(f'make_requests_link <{val}>',type(val))
    return f'<a href="/requests{val}">{val}</a>'

def make_clickable(val, current_sort, descending):
    if current_sort == val and not descending:
        return '<a href="/performance?sort=' + val + '&descending=True">' + val + '▲</a>'
    elif current_sort == val:
        return '<a href="/performance?sort=' + val + '">' + val + '▼</a>'
    else:
        return '<a href="/performance?sort=' + val + '">' + val + '</a>'


@app.route('/performance')
def route_performance():
    print(df.head())
    print('sort', request.args.get('sort'))
    #html_table = df.to_html(escape=False)

    sort_param = request.args.get('sort')
    descending_param = request.args.get('descending') == "True"

    make_clickable_with_current = lambda x: make_clickable(x, sort_param, descending_param)

    if sort_param:
        final_df = df.sort_values(by=[sort_param], ascending=not descending_param)
    else:
        final_df = df

    html_table = (final_df.style
            .format(precision=0, thousands=",") # todo - why is this not working anymore, it was.  might be related to make_requests_link format call 
            .format_index(make_clickable_with_current, axis="columns")
            .set_properties(**{'text-align': 'right'}, subset=df.columns[1:])
            .format({df.columns[0]:make_requests_link}, subset=df.columns[1:])
            .hide_index()
            .render())
    return render_template("performance.html", data=html_table)

@app.route('/requests/<path:path>')
def route_requests(path):
    print(f'path= <{path}>')
    path = f'/{path}'
    request_log_entries = [entry for entry in log_entries if (entry.is_request() or entry.is_response()) and entry.get_deidentified_path() == path]
    for log_entry in request_log_entries[:10]:
        print(f'entry=<{log_entry.get_deidentified_path()}>')
    print(len(request_log_entries))
    return render_template("log-entries.html", log_entries=request_log_entries, log_filter_id=path, log_type='Path')


def api_logs():
    global log_entries
    return log_entries

def column_format(x):
    print(f'column format <{x}>')
    return f'<a href="http://google.com">{x}</a>'


def main():
    parser = argparse.ArgumentParser(description='Reads log file and extracts ')
    # parser.add_argument('--server', action='store', default='', required=False, help='Wildfly log filename')
    # parser.add_argument('--perfmon', action='store', default='', required=False, help='Perfmon4j log filename')
    # parser.add_argument('--aspen', action='store', default='', required=False, help='Aspen log filename')
    parser.add_argument('--data', action='store', default='.', required=False, help='Directory containing log files')
    args = parser.parse_args()
    print(args)
    global log_entries, exceptions_sorted, tool_entries, durations, df, aspen_log_entries

    # print('server: ', glob(f'{args.data}/server.log*'))
    # print('aspen: ', glob('Aspen*.log*', root_dir=args.data))
    # print('perf: ', glob('perfmon4j.log*', root_dir=args.data))

    log_entries = process( glob(f'{args.data}/server.log*'))
    aspen_log_entries = process_aspenlog( glob(f'{args.data}/Aspen*.log*') )
    exceptions_sorted = get_exceptions(log_entries)
    tool_entries = get_tools_and_mark_log_entries_with_concurrent_jobs(log_entries)
    durations = get_durations(log_entries)
    df = get_dataframe(durations)
    print('axes',df.axes)

    # app.add_api("swagger.yaml")
    app.run(debug=True, host='0.0.0.0')

if __name__ == '__main__':
    main()
