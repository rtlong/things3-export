import sqlite3
import os
import sys
import logging

"""

Database Structure:

- TMArea contains areas
- TMTasks contains Projects (type=1), Tasks (type=0) and "ActionGroups" (type=2)
- Tasks are sometimes goruped by actionGroup (i.e. headers)
- some tasks have checklists (which consit of TMChecklistitems)

"""


def export(database):

    logging.basicConfig(filename='export.log', level=logging.DEBUG)

    con = sqlite3.connect(database)

    con.row_factory = sqlite3.Row

    c = con.cursor()
    for row in c.execute(Area.query):
        a = Area(row, con)
        a.export()
    con.close()


class RowObject(object):

    def __init__(self, row, con, level=0):
        self.row = row
        self.con = con
        self.level = level

    def __getattr__(self, name):
        return self.row[name]

    def __getitem__(self, name):
        return getattr(self, name)

    TEMPLATE = '%s%s'

    def indent_(self, level):
        return "\t" * level

    @property
    def indent(self):
        return self.indent_(self.level)

    @property
    def note_indent(self):
        return self.indent_(self.level + 1)


class Area(RowObject):
    query = """
        select uuid, title from TMArea order by "index";
    """

    def export(self):
        # TODO: add switch to skip creating folder and just emit the name
        logging.debug("Area: %s (%s)", self.title, self.uuid)
        self.path = os.path.join('export_data', self.title)
        if not os.path.exists(self.path):
            os.makedirs(self.path)

        c = self.con.cursor()
        for row in c.execute(Project.projects_in_area % self.uuid):
            p = Project(row, self.con, 0, self)
            p.export()


class Project(RowObject):
    projects_in_area = """
        SELECT uuid, status, title, type, notes, area
        FROM TMTask
        WHERE type=1
        AND area="%s"
        AND trashed = 0
        AND status < 2 -- not canceled
        ORDER BY "index";

    """
    PROJECT_TEMPLATE = "\n%(indent)s%(title)s:"
    FILE_TMPL = "%s.taskpaper"

    def __init__(self, row, con, level, area):
        super().__init__(row, con, level)
        self.area = area

    def export(self):
        logging.debug("Project: %s (%s)", self.title, self.uuid)
        filename = self.FILE_TMPL % self.title
        filename = filename.replace(r'/', '|')

        sys.stdout = open(os.path.join(self.area.path, filename), 'w')

        print(self.PROJECT_TEMPLATE % self)
        # TODO: add note
        c = self.con.cursor()
        for row in c.execute(Task.tasks_in_project % self.uuid):
            t = Task(row, self.con, self.level + 1)
            t.export()
        sys.stdout = sys.__stdout__


class Task(RowObject):
    tasks_in_project = """
        SELECT uuid, status, title, type, notes, area
        FROM TMTask
        WHERE type != 1 -- find tasks and action groups
        AND project="%s"
        AND trashed = 0
        AND status < 2 -- whatever "1" means
        ORDER BY type, "index"; -- tasks without headers come first
    """

    tasks_in_action_groups = """
        SELECT uuid, status, title, type, notes, area
        FROM TMTask
        WHERE type = 0
        AND actionGroup="%s"
        AND trashed = 0
        AND status < 2 -- whatever "1" means
        ORDER BY "index";
    """
    ACTIONGROUP = 2
    TASK_TEMPLATE = '%(indent)s- %(title)s'
    ACTIONGROUP_TEMPLATE = '%(indent)s%(title)s (%(uuid)s):'

    def export(self):
        logging.debug("Task: %s (%s) Level: %s Status: %s Type: %s", self.title, self.uuid, self.level, self.status, self.type)
        if self.type == self.ACTIONGROUP:
            # process action group (which have no notes!)
            print(self.ACTIONGROUP_TEMPLATE % self)
            c = self.con.cursor()
            for row in c.execute(Task.tasks_in_project % self.uuid):
                t = Task(row, self.con, self.level + 1)
                t.export()
        else:
            print(self.TASK_TEMPLATE % self)
            if self.notes:
                print(self.notes)  # TODO: convert notes
            # TODO: convert checklists


if __name__ == "__main__":
    things_db = "~/Library/Containers/com.culturedcode.ThingsMac/Data/Library/Application Support/Cultured Code/Things/Things.sqlite3"
    export('Things.sqlite3')
