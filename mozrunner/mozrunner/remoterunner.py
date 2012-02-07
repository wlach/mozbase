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
# The Original Code is Mozilla Corporation Code.
#
# The Initial Developer of the Original Code is
# Mozilla Corporation.
# Portions created by the Initial Developer are Copyright (C) 2008-2011
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#  Joel Maher <joel.maher@gmail.com>
#  Clint Talbert <cmtalbert@gmail.com>
#  William Lachance <wlachance@mozilla.com>
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

import subprocess
import time
from mozprofile import *
import os.path
from runner import Runner

__all__ = [ 'FennecRunner' ]

class FennecRunner(Runner):

    timeout = 3600 # Timeout of 1 hour since android fennec can be slow/unresponsive

    def __init__(self, devicemanager, profile, cmdargs=[], appname="org.mozilla.fennec", clean_profile=True):
        if not appname:
            raise Exception("Must specify appname with remote runner!")

        self.dm = devicemanager
        self.appname = appname
        self.process = None
        self.cmdargs = cmdargs

        self.remote_profile_dir = "/".join([self.dm.getDeviceRoot(), os.path.basename(self.profile.profile)])
        self.clean_profile = clean_profile

        self.timeout

    def is_instance_running(self):
        """Determine if an instance (process) of the application is running"""
        return self.dm.processExist(self.appname)

    def start_instance(self):
        """
        Run an instance of the program in the proper environment
        Will throw an exception if called multiple times and an instance of the
        program is still running
        """
        if self.is_instance_running():
            raise Exception("Instance of %s already running" % self.appname)

        if not self.dm.pushDir(self.profile.profile, self.remote_profile_dir):
            raise Exception("Couldn't copy profile directory")

        fullcmd = [self.appname] + ['-profile', self.remote_profile_dir] + self.cmdargs
        self.dm.launchProcess(fullcmd, failIfRunning=fail_if_running)

    def kill_all_instances(self):
        """Kills all instances of the application"""
        self.dm.killProcess(self.appname)

    def reset(self):
        """
        reset the runner between runs
        currently, only resets the profile, but probably should do more
        """
        self.profile.reset()
