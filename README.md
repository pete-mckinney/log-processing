# log-processing
scripts to manipulate log files and extract tasty goodness

aspenp95.py - Figures out P95 stats for response times in Aspen log.  With --splits, figures out stats for each Aspen path that has been called.

perfmon4csv.py - Parses perfrmon4j log and converts to CSV.

logweb.py - Parses Aspen logs and starts web server for analysis


## todo list
* change parameters for logweb.py to just read directory and figure out context from filenames
* add performance page that shows relative performance of each path