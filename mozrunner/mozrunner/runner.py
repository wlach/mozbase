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
#   William Lachance <wlachance@mozilla.com>
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

__all__ = ['Runner']

# we can replace this method with 'abc'
# (http://docs.python.org/library/abc.html) when we require Python 2.6+
def abstractmethod(method):
  line = method.func_code.co_firstlineno
  filename = method.func_code.co_filename
  def not_implemented(*args, **kwargs):
    raise NotImplementedError('Abstract method %s at File "%s", line %s '
                              'should be implemented by a concrete class' %
                              (repr(method), filename, line))
  return not_implemented

class Runner(object):
    timeout = 600 # arbitrary default 600 second timeout

    def __init__(self, profile):
        self.profile = profile

    @abstractmethod
    def is_instance_running(self):
        """Determine if an instance (process) of the application is running"""

    @abstractmethod
    def start_instance(self):
        """
        Run an instance of the program in the proper environment
        Will throw an exception if called multiple times and an instance of the
        program is still running
        """

    def wait_for_all(self, timeout=None):
        """
        Wait for all instances of the program to exit. Kill all instances if
        timeout exceeded. Timeout may be passed in or, if not set, assigned a
        default value by the implementing class
        """
        if not timeout:
            timeout = self.timeout

        timer = 0
        interval = 5
        while self.is_instance_running():
            time.sleep(interval)
            timer += interval
            if (timer > timeout):
                raise Exception("Timed out waiting for process to finish")


    @abstractmethod
    def kill_all_instances(self):
        """Kill all instances of the program"""

    def reset(self):
        """
        Reset the runner between runs: currently, only resets the profile, but
        probably should do more
        """
        self.profile.reset()
