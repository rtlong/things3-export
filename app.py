# -*- coding: utf-8 -*-
"""
Tkinter wrapper for things2takspaper.

Note: When building a native app with pyinstaller, the working directory of
the app (and of the export script) will be system root ("/"), which is NOT writable, at
least on MacOS. When the app is invoked from the terminal via "open", or
app.py is run with  "python app.py", the working directory is the shell's
current directory.

"""

from argparse import Namespace
import logging
import os
from pathlib import Path
import queue
from textwrap import dedent
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from tkinter import filedialog

import traceback

import export_things

# from setup import VERSION
VERSION = '1.0.2'

logger = logging.getLogger("t2tp")


DATABASE_DIR = '~/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/Things Database.thingsdatabase/'
DATABASE_NAME = 'main.sqlite'
DEFAULT_TARGET = 'Things 3 export'


class App:

    FMT_PROJECT = ("one file per project", "project")
    FMT_AREA = ("one file per area", "area")
    FMT_ALL = ("all in one", "all")

    FORMATS = (FMT_AREA, FMT_PROJECT, FMT_ALL)

    TARGET_FORMAT_FRAME_LABEL = "Output as:"

    EXPLANATION = dedent("""\
        Export your data from the Things 3 database to TaskPaper files.
    """)
    EXPORT_EXPLANATION = dedent("""\
        Please close Things 3 before exporting the database!
        You will find all exported data in your Downloads folder.
    """)
    OPTIONS_EXPLANATION = dedent("""\
        More options:
    """)

    def __init__(self, master):

        self.source_type = None
        self.build_gui(master)

    def build_gui(self, master):
        master.title("Export Things 3 to Taskpaper v%s" % VERSION)

        # convert button and basic explanation: convert
        buttons_frame = tk.Frame(master)
        buttons_frame.pack(fill=tk.BOTH, expand=True)

        T = tk.Text(buttons_frame, height=1, width=90, font=("Helvetica", 16, "normal"))
        T.pack(anchor=tk.NW, padx=10, pady=10)
        T.insert(tk.END, self.EXPLANATION)
        T = tk.Text(buttons_frame, height=2, width=90, font=("Helvetica", 13, "normal"))
        T.pack(anchor=tk.N, expand=True, fill=tk.BOTH, padx=10, pady=5)
        T.insert(tk.END, self.EXPORT_EXPLANATION)

        # file format
        self.format = tk.StringVar()
        self.format_frame = tk.Frame(buttons_frame)
        self.format_frame.pack(anchor=tk.NW, padx=10, pady=10)
        self._make_format_frame(self.format_frame, self.TARGET_FORMAT_FRAME_LABEL, self.format, self.FMT_AREA[1], self.FORMATS)

        self.button_convert = tk.Button(buttons_frame, text="EXPORT", command=self.cmd_things2tp, font=("Helvetica", 13, "normal"), background="#00B0B0", foreground="white")
        self.button_convert.pack(anchor=tk.NW, side=tk.LEFT, padx=5, pady=5)

        # separator
        tk.Frame(height=2, bd=1, relief=tk.SUNKEN).pack(fill=tk.X, padx=5, pady=5)

        file_frame = tk.Frame(master)
        file_frame.pack(fill=tk.BOTH, expand=True)

        self.make_file_frame(file_frame)

        logger_frame = tk.LabelFrame(master, text="Exporter Output:", padx=5, pady=5)
        logger_frame.pack(anchor=tk.NW, fill=tk.X, padx=10, pady=10)
        self.console = ConsoleUi(logger_frame, master)

    def make_file_frame(self, frame):
        # source file
        self.filename = tk.StringVar()

        T = tk.Text(frame, height=1, width=90, font=("Helvetica", 15, "normal"))
        T.pack(anchor=tk.NW, padx=5, pady=5)
        T.insert(tk.END, self.OPTIONS_EXPLANATION)

        # output file
        self.output_file = tk.StringVar()
        output_frame = tk.Frame(frame)
        output_frame.pack(anchor=tk.NW, padx=10, pady=10)
        tk.Label(output_frame, text="Output file ('%s' if empty):" % DEFAULT_TARGET).pack(side=tk.LEFT)
        self.entry_target_file = tk.Entry(output_frame, text="foobar", textvariable=self.output_file)
        self.entry_target_file.pack(side=tk.LEFT, padx=10, pady=10)

        source_frame = tk.Frame(frame)
        source_frame.pack(anchor=tk.NW, padx=10, pady=10)

        tk.Label(source_frame, text="Select custom databases:").pack(side=tk.LEFT)
        tk.Entry(source_frame, text="foobar", textvariable=self.filename).pack(side=tk.LEFT)
        tk.Button(source_frame, text="Select File", command=self.cb_select_file).pack(side=tk.LEFT)

    def _make_format_frame(self, frame, label, variable, default, available_formats):
        """Set available output formats."""
        variable.set(default)
        tk.Label(frame, text=label).pack(side=tk.LEFT)
        for text, mode in available_formats:
            tk.Radiobutton(frame, text=text, variable=variable, value=mode).pack(side=tk.LEFT)

    def clean_frame(self, frame):
        for widget in frame.winfo_children():
            widget.destroy()

    def cb_select_file(self):
        filename = tk.filedialog.askopenfilename(initialdir=os.path.join(Path.home(), "Documents"),
                                                 title="Select file",
                                                 defaultextension='*.sqlite3',
                                                 filetypes=(("SQLite3 Files", "*.sqlite3"),
                                                            ("SQLite Files", "*.sqlite")))
        self.filename.set(filename)

    def cmd_things2tp(self):
        """Export the database. This is called when pressing the Export button"""
        logger.setLevel('INFO')
        # logger.setLevel('DEBUG')
        logger.info("starting conversion...")

        database = self.filename.get()
        if not database:
            database = os.path.join(os.path.expanduser(DATABASE_DIR), DATABASE_NAME)
            logger.info("no databases selected, setting default database")

        if not os.path.exists(database):
            logger.error("database '%s' does not exist!" % database)
            return
        logger.info("database: %s" % database)

        output_format = self.format.get()
        logger.info("target format: %s" % output_format)
        if output_format not in [self.FMT_ALL[1], self.FMT_PROJECT[1], self.FMT_AREA[1]]:
            logger.error("unknown output format: %s" % output_format)
            return

        target = self.output_file.get()
        if not target:
            target = DEFAULT_TARGET
        # capture stdout if all-in-one
        if output_format == self.FMT_ALL[1]:
            target = export_things.RowObject.FILE_TMPL % target
        target = os.path.join(Path.home(), "Downloads", target)
        logger.info("target: %s" % target)

        args = Namespace(database=database,
                         target=target,
                         format=output_format,
                         stdout=False,
                         called_from_gui=True)
        try:
            export_things.export(args)
        except Exception:
            tb = traceback.format_exc()
            logger.error(tb)
        else:
            logger.info("export finished")

        logger.info("ready")


class QueueHandler(logging.Handler):
    """Class to send logging records to a queue

    It can be used from different threads
    """
    def __init__(self, log_queue):
        super(QueueHandler, self).__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(record)


class ConsoleUi:
    """Poll messages from a logging queue and display them in a scrolled text widget"""

    def __init__(self, frame, master):
        self.frame = frame
        # Create a ScrolledText wdiget
        self.scrolled_text = ScrolledText(frame, state='disabled', height=12)
        self.scrolled_text.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.W, tk.E))
        self.scrolled_text.configure(font='TkFixedFont')
        self.scrolled_text.tag_config('INFO', foreground='black')
        self.scrolled_text.tag_config('DEBUG', foreground='gray')
        self.scrolled_text.tag_config('WARNING', foreground='orange')
        self.scrolled_text.tag_config('ERROR', foreground='red')
        self.scrolled_text.tag_config('CRITICAL', foreground='red', underline=1)
        # Create a logging handler using a queue
        self.log_queue = queue.Queue()
        self.queue_handler = QueueHandler(self.log_queue)
        formatter = logging.Formatter('%(message)s')
        self.queue_handler.setFormatter(formatter)
        logger.addHandler(self.queue_handler)
        # Start polling messages from the queue
        self.frame.after(100, self.poll_log_queue)
        self.scrolled_text.pack(fill=tk.BOTH, expand=1)
        self.button_quit = tk.Button(self.frame, text="Quit", fg="red", command=master.quit)
        self.button_quit.pack(anchor=tk.NE, side=tk.RIGHT)

    def display(self, record):
        msg = self.queue_handler.format(record)
        self.scrolled_text.configure(state='normal')
        self.scrolled_text.insert(tk.END, msg + '\n', record.levelname)
        self.scrolled_text.configure(state='disabled')
        # Autoscroll to the bottom
        self.scrolled_text.yview(tk.END)

    def poll_log_queue(self):
        # Check every 100ms if there is a new message in the queue to display
        while True:
            try:
                record = self.log_queue.get(block=False)
            except queue.Empty:
                break
            else:
                self.display(record)
        self.frame.after(100, self.poll_log_queue)


def main():
    root = tk.Tk()
    App(root)

    # begin workaround code
    def fix_macos_mojave_button_issue():
        """See https://stackoverflow.com/questions/52529403/button-text-of-tkinter-does-not-work-in-mojave"""
        a = root.winfo_geometry().split('+')[0]
        b = a.split('x')
        w = int(b[0])
        h = int(b[1])
        root.geometry('%dx%d' % (w + 1, h + 1))
    root.update()
    root.after(0, fix_macos_mojave_button_issue)
    # end of workaround code

    os.system('''/usr/bin/osascript -e 'tell app "Finder" to set frontmost of process "python" to true' ''')
    root.mainloop()
    root.destroy()


if __name__ == "__main__":
    main()
