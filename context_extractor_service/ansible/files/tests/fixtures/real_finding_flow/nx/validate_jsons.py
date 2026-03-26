import os
import subprocess
from subprocess import PIPE
from fnmatch import fnmatch


def validate_jsons(root, exclude, pattern):
    for path, subdirs, files in os.walk(root, topdown=True):
        subdirs[:] = [d for d in subdirs if d not in exclude]
        for name in files:
            if fnmatch(name, pattern):
                p = subprocess.Popen('jsonlint -v --nonstrict %s' % os.path.join(path, name), shell=True, stdout=PIPE)
                out, err = p.communicate()
                print(out)
                print(err)
                p.wait()
