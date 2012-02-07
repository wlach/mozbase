# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is mozrunner.
#
# The Initial Developer of the Original Code is
#   The Mozilla Foundation.
# Portions created by the Initial Developer are Copyright (C) 2008-2009
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Mikeal Rogers <mikeal.rogers@gmail.com>
#   Clint Talbert <ctalbert@mozilla.com>
#   Henrik Skupin <hskupin@mozilla.com>
#   Jeff Hammel <jhammel@mozilla.com>
#   Andrew Halberstadt <halbersa@gmail.com>
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****

__all__ = ['DesktopRunner', 'ThunderbirdRunner', 'FirefoxRunner']

import mozinfo
import os
import platform
import sys
import ConfigParser

from utils import get_metadata_from_egg
from utils import findInPath
from mozprofile import *
from mozprocess.processhandler import ProcessHandler
from runner import Runner

def get_processes_running(command_names):
    processes_running = []

    for command_name in command_names:
        if mozinfo.isWin:
            import win32pdhutil
            try:
                # FIXME: this is from pywin32, which we shouldn't actually be using.
                # enhance winprocess.py in mozprocess instead?
                win32pdh.EnumObjects(None, None, 0, 1) # refresh list of processes
                pids = win32pdhutil.FindPerformanceAttributesByName(command_name, counter="ID Process")
                for pid in pids:
                    processes_running.append((pid, command_name))
            except:
                # Might get an exception if there are no instances of the process running.
                continue
        else:
            # FIXME: Use mozprocess.pid here? ps would seem to be what we want to use,
            # but it doesn't currently return the command line (comm)
            # FIXME: only tested on Linux, it should work on mac, but verify this
            p = subprocess.Popen(['ps', '-eo' ,'pid,comm'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, notused = p.communicate()
            for line in stdout.splitlines()[1:-1]:
                pid, command = line.split()
                if command in command_names:
                    processes_running.append((pid, command_name))

    return processes_running

class DesktopRunner(Runner):
    """Handles all running operations. Finds bins, runs and kills the process."""

    profile_class = Profile # profile class to use by default
    timeout = 600

    @classmethod
    def create(cls, binary, cmdargs=None, env=None, kp_kwargs=None, profile_args=None,
                                               clean_profile=True, process_class=ProcessHandler):
        profile = cls.profile_class(**(profile_args or {}))
        return cls(profile, binary=binary, cmdargs=cmdargs, env=env, kp_kwargs=kp_kwargs,
                                           clean_profile=clean_profile, process_class=process_class)

    def __init__(self, profile, binary, cmdargs=None, env=None,
                 kp_kwargs=None, clean_profile=True, process_class=ProcessHandler):
        self.process_handler = None
        self.process_class = process_class
        self.profile = profile
        self.clean_profile = clean_profile

        # find the binary
        self.binary = binary
        if not self.binary:
            raise Exception("Binary not specified")
        if not os.path.exists(self.binary):
            raise OSError("Binary path does not exist: %s" % self.binary)

        self.cmdargs = cmdargs or []
        _cmdargs = [i for i in self.cmdargs
                    if i != '-foreground']
        if len(_cmdargs) != len(self.cmdargs):
            # foreground should be last; see
            # - https://bugzilla.mozilla.org/show_bug.cgi?id=625614
            # - https://bugzilla.mozilla.org/show_bug.cgi?id=626826
            self.cmdargs = _cmdargs
            self.cmdargs.append('-foreground')

        # process environment
        if env is None:
            self.env = os.environ.copy()
        else:
            self.env = env.copy()
        # allows you to run an instance of Firefox separately from any other instances
        self.env['MOZ_NO_REMOTE'] = '1'
        # keeps Firefox attached to the terminal window after it starts
        self.env['NO_EM_RESTART'] = '1'

        # set the library path if needed on linux
        if sys.platform == 'linux2' and self.binary.endswith('-bin'):
            dirname = os.path.dirname(self.binary)
            if os.environ.get('LD_LIBRARY_PATH', None):
                self.env['LD_LIBRARY_PATH'] = '%s:%s' % (os.environ['LD_LIBRARY_PATH'], dirname)
            else:
                self.env['LD_LIBRARY_PATH'] = dirname

        # arguments for ProfessHandler.Process
        self.kp_kwargs = kp_kwargs or {}

    # Base Runner implementation

    def is_instance_running(self):
        """Determine if an instance (process) of the application is running"""
        return len(get_processes_running(os.path.basename(self.binary))) > 0

    def start_instance(self):
        """
        Run an instance of the program in the proper environment
        May throw an exception if called multiple times and an instance of the
        program is still running
        """
        if self.is_running():
            raise Exception("Instance of the process is still running")
        else:
            self.start()

    def kill_all_instances(self):
        """Kill all instances of the program"""

        # Kill ourselves first
        self.stop()

        processes_running = get_processes_running(os.path.basename(self.binary))
        for process in processes_running:
            if mozinfo.isWin:
                # FIXME: as above, this depends on pywin32, which it probably shouldn't
                import win32api
                PROCESS_TERMINATE = 1
                handle = win32api.OpenProcess(PROCESS_TERMINATE, False, pid)
                win32api.TerminateProcess(handle, -1)
                win32api.CloseHandle(handle)
            else:
                os.kill(process[0])

    # DesktopRunner specific methods

    @property
    def command(self):
        """Returns the command list to run."""
        return [self.binary, '-profile', self.profile.profile]

    def get_repositoryInfo(self):
        """Read repository information from application.ini and platform.ini."""

        config = ConfigParser.RawConfigParser()
        dirname = os.path.dirname(self.binary)
        repository = { }

        for file, section in [('application', 'App'), ('platform', 'Build')]:
            config.read(os.path.join(dirname, '%s.ini' % file))

            for key, id in [('SourceRepository', 'repository'),
                            ('SourceStamp', 'changeset')]:
                try:
                    repository['%s_%s' % (file, id)] = config.get(section, key);
                except:
                    repository['%s_%s' % (file, id)] = None

        return repository

    def is_running(self):
        """Determine if the process launched by this runner instance is running"""
        return self.process_handler is not None

    def start(self):
        """Run self.command in the proper environment."""

        # ensure you are stopped
        self.stop()

        # ensure the profile exists
        if not self.profile.exists():
            self.profile.reset()
        
        cmd = self._wrap_command(self.command+self.cmdargs)
        # this run uses the managed processhandler
        self.process_handler = self.process_class(cmd, env=self.env, **self.kp_kwargs)
        self.process_handler.run()

    def wait(self, timeout=None, outputTimeout=None):
        """Wait for the app to exit."""
        if self.process_handler is None:
            return
        self.process_handler.waitForFinish(timeout=timeout, outputTimeout=outputTimeout)
        self.process_handler = None

    def stop(self):
        """Kill the app"""
        if self.process_handler is None:
            return
        self.process_handler.kill()
        self.process_handler = None

    def reset(self):
        """
        reset the runner between runs
        currently, only resets the profile, but probably should do more
        """
        self.profile.reset()

    def cleanup(self):
        self.stop()
        if self.clean_profile:
            self.profile.cleanup()

    def _wrap_command(self, cmd):
        """
        If running on OS X 10.5 or older, wrap |cmd| so that it will
        be executed as an i386 binary, in case it's a 32-bit/64-bit universal
        binary.
        """
        if mozinfo.isMac and hasattr(platform, 'mac_ver') and \
                               platform.mac_ver()[0][:4] < '10.6':
            return ["arch", "-arch", "i386"] + cmd
        return cmd

    __del__ = cleanup


class FirefoxRunner(DesktopRunner):
    """Specialized Runner subclass for running Firefox."""

    profile_class = FirefoxProfile

    def __init__(self, profile, binary=None, **kwargs):

        # take the binary from BROWSER_PATH environment variable
        if (not binary) and 'BROWSER_PATH' in os.environ:
            binary = os.environ['BROWSER_PATH']

        DesktopRunner.__init__(self, profile, binary, **kwargs)

        # Find application version number
        appdir = os.path.dirname(os.path.realpath(self.binary))
        appini = ConfigParser.RawConfigParser()
        appini.read(os.path.join(appdir, 'application.ini'))
        # Version needs to be of the form 3.6 or 4.0b and not the whole string
        version = appini.get('App', 'Version').rstrip('0123456789pre').rstrip('.')

        # Disable compatibility check. See:
        # - http://kb.mozillazine.org/Extensions.checkCompatibility
        # - https://bugzilla.mozilla.org/show_bug.cgi?id=659048
        preference = {'extensions.checkCompatibility.' + version: False,
                      'extensions.checkCompatibility.nightly': False}
        self.profile.set_preferences(preference)


class ThunderbirdRunner(DesktopRunner):
    """Specialized Runner subclass for running Thunderbird"""
    profile_class = ThunderbirdProfile

