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

__all__ = [ 'RemoteFennecRunner' ]

class RemoteException(Exception):
    """exception for interacting with remote device"""
    def __init__(self, msg = ''):
        self.msg = msg

    def __str__(self):
        return self.msg

class RemoteFennecRunner(object):
    """Handles all running operations. Runs and kills the process."""

    def __init__(self, devicemanager, profile, cmdargs=[], appname="org.mozilla.fennec", clean_profile=True):
        self.dm = devicemanager
        self.appname=appname
        self.process = None
        self.cmdargs = cmdargs

        self.profile = profile
        self.remote_profile_dir = "/".join([self.dm.getDeviceRoot(), os.path.basename(self.profile.profile)])
        self.clean_profile = clean_profile

        # Setting timeout at 1 hour since on a remote device this takes much longer
        self.timeout = 3600

    def is_running(self):
        """Determine if process is (still) running"""
        return self.dm.processExist(self.appname)

    def start(self, fail_if_running=False):
        """Run fennec in the proper environment."""
        if not self.dm.pushDir(self.profile.profile, self.remote_profile_dir):
            raise RemoteException("Couldn't copy profile directory")

        fullcmd = [self.appname] + ['-profile', self.remote_profile_dir] + self.cmdargs
        self.dm.launchProcess(fullcmd, failIfRunning=fail_if_running)

    def wait(self, timeout=None, outputTimeout=None):
        """Wait for the app to exit"""
        if not timeout:
            timeout = self.timeout

        timer = 0
        interval = 5
        while self.is_running():
            time.sleep(interval)
            timer += interval
            if (timer > timeout):
                raise RemoteException("Timed out waiting for process to finish")

    def stop(self):
        """Kill the app"""
        self.dm.killProcess(self.appname)

    def cleanup(self):
        self.stop()
        if self.clean_profile:
            self.profile.cleanup()

    __del__ = cleanup

