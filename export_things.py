import argparse
from datetime import datetime, date
import logging
import os
import re
import sqlite3
import sys
from math import floor

"""
Export Things 3 database to TaskPaper files

Things 3 database can be found at:
~/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/Things Database.thingsdatabase/main.sqlite

before Things 3.13 it was at 
~/Library/Containers/com.culturedcode.ThingsMac/Data/Library/Application Support/Cultured Code/Things/Things.sqlite3

Database Structure:

- TMArea contains areas
- TMTasks contains Projects (type=1), Tasks (type=0) and "headers" (type=2)
- Tasks are sometimes goruped by header (i.e. headers)
- some tasks have checklists (which consit of TMChecklistitems)

"""

DEFAULT_TARGET = 'Things3 export'


def export(args):
    try:
        args.called_from_gui
    except:
        # log to file only if not called from guo
        logging.basicConfig(filename='export.log', level=logging.DEBUG)

    con = sqlite3.connect(args.database)

    con.row_factory = sqlite3.Row

    c = con.cursor()
    no_area = Area(dict(uuid='NULL', title='no area'), con, args)
    no_area.export()
    for row in c.execute(Area.QUERY):
        a = Area(row, con, args)
        a.export()
    con.close()

class RowObject(object):
    FMT_ALL = 'all'
    FMT_PROJECT = 'project'
    FMT_AREA = 'area'

    def __init__(self, row, con, args, level=0):
        self.row = row
        self.con = con
        self.args = args
        self.level = level

    def __getattr__(self, name):
        return self.row[name]

    def __getitem__(self, name):
        return getattr(self, name)

    TEMPLATE = '%s%s'

    def indent_(self, level):
        return "*" + "*" * level + " "

    @property
    def indent(self):
        return self.indent_(self.level)

    @property
    def notes_indent(self):
        return ""
        # return " "(self.level + 1)

    @property
    def tags(self):
        return ''  # tags are empty for some items

    URL = re.compile("\<a href=\"(?P<url>.*)?\"\>.*?\<\/a\>")

    def print_notes(self):
        notes = self.notes
        if notes.startswith("<note xml:space=\"preserve\">"):
            notes = notes[27:-7]
        for line in notes.split("\n"):
            line = self.URL.sub(lambda m: m.group('url'), line)
            print('%s%s' % (self.notes_indent, line))

    def find_and_export_items(self, klass, query):
        c = self.con.cursor()
        for row in c.execute(query):
            item = klass(row, self.con, self.args, self.level + 1)
            item.export()


class RowObjectWithTags(RowObject):

    TAGS_QUERY = """
        SELECT tag.title AS title FROM TMTaskTag AS tt, TMTag AS tag
        WHERE tt.tasks = '%s'
        AND tt.tags = tag.uuid;
    """

    def __init__(self, row, con, args, level=0):
        super().__init__(row, con, args, level)
        self._tags = []

    @property
    def tags(self):
        if len(self._tags) == 0:
            return ''
        return ' :' + ':'.join(self._tags) + ":"

    def add_tag(self, tag):
        if tag not in self._tags:
            self._tags.append(tag)

    def load_tags_from_db(self):
        def make_tag(title):
            return  title.replace(' ', '_').replace('-', '_')

        c = self.con.cursor()
        for row in c.execute(self.TAGS_QUERY % self.uuid):
            self.add_tag(make_tag(row['title']))


class TaskObjects(RowObjectWithTags):

    task_fields = """
        SELECT uuid, status, title, type, notes, area, deadline, startDate, todayIndex, checklistItemsCount, stopDate, start
        FROM TMTask
    """

    def __init__(self, row, con, args, level=0):
        super().__init__(row, con, args, level)
        self._priority = None;
        self._blocked = None;
        self._idea = False;

    @property
    def org_todo_keyword(self):
        if self._idea:
            return "IDEA"
        if self._blocked:
            return "BLOCKED"
        if self.start== 2:
            return "LATER"
        else:
            return "TODO"

    @property
    def org_priority_cookie(self):
        if self._priority is not None:
            return " [#%(_priority)s]" % self
        return ""

    def add_tag(self, tag):
        if tag == "Idea":
            self._idea = True
            return
        if tag == "Important":
            self._priority = 1
            return
        if tag == "Blocked":
            self._blocked = True
            return
        super().add_tag(tag)

    def parse_db_date(self, ts_int): 
        # Things uses a bespoke numeric Date encoding 
        DAYS = 128;
        MONTHS = 32 * DAYS;
        YEARS = 16 * MONTHS;

        year = floor(ts_int / YEARS)
        ts_int -= year * YEARS;
        month = floor(ts_int / MONTHS)
        ts_int -= month * MONTHS;
        day = floor(ts_int / DAYS)

        return date(year, month, day)


    def print_attributes(self):
        """Add all attributes (due date, start date, today, someday etc.) as tags."""
        if self.deadline:
            print("DEADLINE: <%s>" % self.parse_db_date(self.deadline).strftime("%Y-%m-%d %a"))
        if self.startDate:
            print("SCHEDULED: <%s>" % self.parse_db_date(self.startDate).strftime("%Y-%m-%d %a"))


class Area(RowObjectWithTags):
    QUERY = """
        SELECT uuid, title FROM TMArea ORDER BY "index";
    """

    TAGS_QUERY = """
        SELECT tag.title AS title FROM TMAreaTag AS at, TMTag AS tag
        WHERE at.areas = '%s'
        AND at.tags = tag.uuid;
    """
    AREA_TEMPLATE = "\n%(indent)s%(title)s:%(tags)s"

    def export(self):
        logging.debug("Area: %s (%s)", self.title, self.uuid)
        self.load_tags_from_db()
        next_level = 1
        print(self.AREA_TEMPLATE % self)

        c = self.con.cursor()

        if self.uuid == 'NULL':
            inbox = Project(dict(uuid='NULL', title='Inbox',
                                 deadline=None, startDate=None, stopDate=None, todayIndex=None, notes=None, start=None),
                            self.con, self.args, self.level + 1, self)
            inbox.export()
            query = Project.PROJECTS_WITHOUT_AREA
        else:
            self.find_and_export_items(Task, Task.TASKS_IN_AREA_WITHOUT_PROJECT % self.uuid)
            query = Project.PROJECTS_IN_AREA % self.uuid

        for row in c.execute(query):
            p = Project(row, self.con, self.args, next_level, self)
            p.export()



class Project(TaskObjects):
    PROJECTS_IN_AREA = TaskObjects.task_fields + """
        WHERE type=1
        AND area="%s"
        AND trashed = 0
        AND status < 2 -- not canceled
        ORDER BY "index";
    """
    PROJECTS_WITHOUT_AREA = TaskObjects.task_fields + """
        WHERE type=1
        AND area is NULL
        AND trashed = 0
        AND status < 2 -- not canceled
        ORDER BY "index";
    """

    PROJECT_TEMPLATE = "\n%(indent)s%(org_todo_keyword)s%(org_priority_cookie)s %(title)s%(tags)s"

    def __init__(self, row, con, args, level, area):
        super().__init__(row, con, args, level)
        self.area = area

    def export(self):
        logging.debug("Project: %s (%s)", self.title, self.uuid)
        self.load_tags_from_db()
        print(self.PROJECT_TEMPLATE % self)
        self.print_attributes()

        if self.notes:
            self.print_notes()

        if self.uuid == 'NULL':
            self.find_and_export_items(Task, Task.TASKS_IN_INBOX)
        else:
            self.find_and_export_items(Task, Task.TASKS_IN_PROJECT % self.uuid)



class Task(TaskObjects):

    TASKS_IN_PROJECT = TaskObjects.task_fields + """
        WHERE type != 1 -- find tasks and action groups
        AND project="%s"
        AND trashed = 0
        AND status < 2 -- whatever "1" means
        ORDER BY type, "index"; -- tasks without headers come first
    """
    TASKS_IN_AREA_WITHOUT_PROJECT = TaskObjects.task_fields + """
        WHERE type != 1 -- find tasks and action groups
        AND area="%s"
        AND project is NULL
        AND trashed = 0
        AND status < 2 -- whatever "1" means
        ORDER BY type, "index"; -- tasks without headers come first
    """
    TASKS_IN_INBOX = TaskObjects.task_fields + """
        WHERE type != 1 -- find tasks and action groups
        AND project IS NULL
        AND area IS NULL
        AND heading IS NULL
        AND trashed = 0
        AND status < 2 -- whatever "1" means
        ORDER BY "index";
    """
    TASKS_IN_ACTION_GROUPS = TaskObjects.task_fields + """
        WHERE type = 0
        AND heading="%s"
        AND trashed = 0
        AND status < 2 -- whatever "1" means
        ORDER BY "index";
    """
    ACTIONGROUP = 2
    TASK_TEMPLATE = '%(indent)s%(org_todo_keyword)s%(org_priority_cookie)s %(title)s%(tags)s'
    ACTIONGROUP_TEMPLATE = '%(indent)sTODO %(title)s:'


    def export(self):
        logging.debug("Task: %s (%s) Level: %s Status: %s Type: %s, Start: %s Deadline: %s StartDate: %s", self.title, self.uuid, self.level, self.status, self.type, self.start, self.deadline, self.startDate)
        self.load_tags_from_db()
        if self.type == self.ACTIONGROUP:
            # process action group (which have no notes!)
            print(self.ACTIONGROUP_TEMPLATE % self)
            self.find_and_export_items(Task, Task.TASKS_IN_ACTION_GROUPS % self.uuid)
        else:
            print(self.TASK_TEMPLATE % self)
            self.print_attributes()
            if self.notes:
                self.print_notes()

            if self.checkListItemsCount:
                self.find_and_export_items(CheckListItem, CheckListItem.items_of_task % self.uuid)


class CheckListItem(RowObject):
    items_of_task = """
        SELECT uuid, title, status
        FROM TMChecklistItem
        WHERE task = '%s'
        ORDER BY "index"
    """

    def indent_(self, level):
        return ""

    @property
    def checkbox_status(self): 
        if self.status > 0:
            return "X"
        else:
            return " "

    CHECKLIST_ITEM_TEMPLATE = '%(indent)s- [%(checkbox_status)s] %(title)s%(tags)s'

    def export(self):
        print(self.CHECKLIST_ITEM_TEMPLATE % self)



if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Export tasks from Things3 database to TaskPaper.')
    parser.add_argument('--target', dest='target', action='store',
                        default=DEFAULT_TARGET,
                        help='output folder (default: export_data')
    parser.add_argument('--db', dest='database', action='store',
                        default='main.sqlite',
                        help='path to the Things3 database (default: main.sqlite)')

    args = parser.parse_args()
    export(args)
