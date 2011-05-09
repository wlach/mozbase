import subprocess
import os
import signal
import sys
import select
import types
import threading
import logging
from Queue import Queue
from datetime import datetime, timedelta

import pdb

if sys.platform == 'win32':
    import ctypes, ctypes.wintypes, time, msvcrt
    from ctypes import sizeof, addressof, c_ulong, byref, POINTER, WinError
    import winprocess
    from qijo import JobObjectAssociateCompletionPortInformation, JOBOBJECT_ASSOCIATE_COMPLETION_PORT

class ProcessHandler(object):
    """Class which represents a process to be executed."""

    class Process(subprocess.Popen):
        """
        Represents our view of a subprocess.
        It adds a kill() method which allows it to be stopped explicitly.
        """

        def __init__(self,
                     args,
                     bufsize=0,
                     executable=None,
                     stdin=None,
                     stdout=None,
                     stderr=None,
                     preexec_fn=None,
                     close_fds=False,
                     shell=False,
                     cwd=None,
                     env=None,
                     universal_newlines=False,
                     startupinfo=None,
                     creationflags=0,
                     ignore_children=False,
                     logger = None):
            # Parameter for whether or not we should attempt to track child processes
            self._ignore_children = ignore_children
            
            # Our logging module, if it is None, we use the system logger
            if (logger):
                self.logger = logger
            else:
                self.logger = logging

            # Odd workaround for mac - TODO: Figure out why this exists
            self.kill_called = False

            if (not self._ignore_children and sys.platform is not 'win32'):
                # Set the process group id for linux systems
                # Sets process group id to the pid of the parent process
                # NOTE: This prevents you from using preexec_fn and managing 
                #       child processes, TODO: Ideally, find a way around this
                preexec_fn = os.setpgid(0,0)

            subprocess.Popen.__init__(self, args, bufsize, executable,
                                      stdin, stdout, stderr,
                                      preexec_fn, close_fds,
                                      shell, cwd, env,
                                      universal_newlines, startupinfo, creationflags)

        def kill(self):
            self.returncode = 0
            if sys.platform == 'win32':
                if not self._ignore_children and self._job:
                    winprocess.TerminateJobObject(self._job, winprocess.ERROR_CONTROL_C_EXIT)
                    self.returncode = winprocess.GetExitCodeProcess(self._handle)
                else:
                    try:
                        winprocess.TerminateProcess(self._handle, winprocess.ERROR_CONTROL_C_EXIT)
                    except:
                        # TODO: Throw?
                        self.logger.warn("Could not terminate process")
                    finally:
                        self.returncode = winprocess.GetExitCodeProcess(self._handle)
            else:
                # TODO: Figure out why mac needs this workaround
                self.kill_called = True
                if not self._ignore_children:
                    try:
                        os.killpg(self.pid, signal.SIGKILL)
                    except:
                        self.logger.warn("Could not kill process: %s" % self.pid)
                    finally:
                        self.returncode = -9
                else:
                    os.kill(self.pid, signal.SIGKILL)
                    self.returncode = -9
                 
            return self.returncode

        def wait(self, timeout=None):
            """ Popen.wait
                Called to wait for a running process to shut down and return
                its exit code
                Returns the main process's exit code
            """
            # This call will be different for each OS
            self.returncode = self._wait(timeout=timeout)
            return self.returncode

        """ Private Members of Process class """
        def _timed_wait_callback(self, callback_func, timeout):
            """ This function is used by linux and mac to handle their wait code.
                It runs a wait loop with the given timeout and calls back into
                a function (callback_func) with the given timeout parmeter
            """
            if timeout is None:
                if not self._ignore_children:
                    return callback_func(timeout)
                else:
                    # For non-group wait, call base class
                    subprocess.Popen.wait(self)
                    return self.returncode
            done = False
            
            now = datetime.datetime.now()
            starttime = datetime.datetime.now()
            diff = now - starttime
            while (((diff.seconds * 100 * 1000 + diff.microseconds) < timeout * 1000 * 1000) and
                   done is False):
                if not self._ignore_children:
                    return callback_func(timeout)
                else:
                    if subprocess.poll() is not None:
                        done = self.returncode
                time.sleep(.5)
                now = datetime.datetime.now()
                diff = now - starttime
            return self.returncode

        if sys.platform == 'win32':
            # Redefine the execute child so that we can track process groups
            def _execute_child(self, args, executable, preexec_fn, close_fds,
                               cwd, env, universal_newlines, startupinfo,
                               creationflags, shell,
                               p2cread, p2cwrite,
                               c2pread, c2pwrite,
                               errread, errwrite):
                if not isinstance(args, types.StringTypes):
                    args = subprocess.list2cmdline(args)
                
                # Always or in the create new process group
                creationflags |= winprocess.CREATE_NEW_PROCESS_GROUP

                if startupinfo is None:
                    startupinfo = winprocess.STARTUPINFO()

                if None not in (p2cread, c2pwrite, errwrite):
                    startupinfo.dwFlags |= winprocess.STARTF_USESTDHANDLES
                    startupinfo.hStdInput = int(p2cread)
                    startupinfo.hStdOutput = int(c2pwrite)
                    startupinfo.hStdError = int(errwrite)
                if shell:
                    startupinfo.dwFlags |= winprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = winprocess.SW_HIDE
                    comspec = os.environ.get("COMSPEC", "cmd.exe")
                    args = comspec + " /c " + args

                # determine if we can create create a job
                canCreateJob = winprocess.CanCreateJobObject()

                # Ensure we write a warning message if we are falling back
                if not canCreateJob and not self._ignore_children:
                    # We can't create job objects AND the user wanted us to
                    # Warn the user about this. (this will end up on the console)
                    self.logger.warn("ProcessManager UNABLE to use job objects to manage child processes")

                # set process creation flags
                creationflags |= winprocess.CREATE_SUSPENDED
                creationflags |= winprocess.CREATE_UNICODE_ENVIRONMENT
                if canCreateJob:
                    self.logger.info("ProcessManager using job objects to manage child processes")
                    creationflags |= winprocess.CREATE_BREAKAWAY_FROM_JOB
                else:
                    # Since we've warned, we just log info here to inform you
                    # of the consequence of setting ignore_children = True
                    self.logger.info("ProcessManager NOT managing child processes")

                # create the process
                hp, ht, pid, tid = winprocess.CreateProcess(
                    executable, args,
                    None, None, # No special security
                    1, # Must inherit handles!
                    creationflags,
                    winprocess.EnvironmentBlock(env),
                    cwd, startupinfo)
                self._child_created = True
                self._handle = hp
                self._thread = ht
                self.pid = pid
                self.tid = tid

                if canCreateJob:
                    try:
                        # We create a new job for this process, so that we can kill
                        # the process and any sub-processes                    
                        # Create the IO Completion Port
                        self._io_port = winprocess.CreateIoCompletionPort()
                        self._job = winprocess.CreateJobObject()

                        # Now associate the io comp port and the job object
                        joacp = JOBOBJECT_ASSOCIATE_COMPLETION_PORT(winprocess.COMPKEY_JOBOBJECT,
                                                                    self._io_port)
                        winprocess.SetInformationJobObject(self._job,
                                                          JobObjectAssociateCompletionPortInformation,
                                                          addressof(joacp),
                                                          sizeof(joacp)
                                                          )

                        # Assign the job object to the process
                        winprocess.AssignProcessToJobObject(self._job, int(hp))

                        # Spin up our thread for managing the IO Completion Port
                        self._procmgrthread = threading.Thread(target = self._procmgr)
                    except:
                        self.logger.warn("Exception trying to use job objects, \
                                          falling back to not using job objects for \
                                          managing child processes")
                        # Ensure no dangling handles left behind
                        self._cleanup_job_and_io_port()
                else:
                    self._job = None
                        
                winprocess.ResumeThread(int(ht))
                if (self._procmgrthread):
                    self._procmgrthread.start()
                ht.Close()

                if p2cread is not None:
                    p2cread.Close()
                if c2pwrite is not None:
                    c2pwrite.Close()
                if errwrite is not None:
                    errwrite.Close()
                time.sleep(.1)
          
            # Windows Process Manager - watches the IO Completion Port and
            # keeps track of child processes
            def _procmgr(self):
                if not (self._io_port) or not (self._job):
                    return
                # It's overkill, but we use Queue to signal between threads
                # because it handles errors more gracefully than event or condition.
                self._process_events = Queue()
                try:
                    self._poll_iocompletion_port()
                except KeyboardInterrupt:
                    print "Keyboard interrupt"

            def _poll_iocompletion_port(self):
                # Watch the IO Completion port for status
                # TODO: This should probably be a while not done: loop, and 
                # done should be set on a "zero processes left" or on an error
                # or on a number of times after a kill has been posted.  For example:
                # once you call kill it sets "finish up" and once this loop sees "finish up"
                # it runs 2-3 more loops before throwing an exception and killing itself
                # that way this thread won't run forever. (Ideally we'd get the msg 4 (no processes remaining)
                # before we exhaust our "finish up"
                while (True):
                    msgid = c_ulong(0)
                    compkey = c_ulong(0)
                    pid = c_ulong(0)

                    portstatus = winprocess.GetQueuedCompletionStatus(self._io_port,
                                                                      byref(msgid),
                                                                      byref(compkey),
                                                                      byref(pid),
                                                                      10000)

                    if (not portstatus):
                        # Check to see what happened
                        errcode = winprocess.GetLastError()
                        if errcode == winprocess.ERROR_ABANDONED_WAIT_0:
                            # Then something has killed the port, break the loop
                            self.logger.warn("IO Completion Port unexpectedly closed")
                            break
                        elif errcode == winprocess.WAIT_TIMEOUT:
                            print "continuing polling"
                            # Timeouts are expected, just keep on polling
                            continue
                        else:
                            self.logger.warn("Error Code %s trying to query IO Completion Port, exiting" % errcode)
                            print "Got Error code %s trying to query IO Completion port" % errcode
                            break

                    if compkey.value == winprocess.COMPKEY_TERMINATE.value:
                        print "compkey_terminate encountered"
                        # Then we're done
                        break
                    
                    # Check the status of the IO Port and do things based on it
                    if (compkey.value == winprocess.COMPKEY_JOBOBJECT.value):
                        if (msgid.value == winprocess.JOB_OBJECT_MSG_ACTIVE_PROCESS_ZERO):
                            # No processes left, time to shut down
                            # Signal anyone waiting on us that it is safe to shut down
                            self._process_events.put({self._procmgrthread.ident: 'FINISHED'})
                            print "winproc: no procs left, shutting down"
                            break
                        elif (msgid.value == winprocess.JOB_OBJECT_MSG_NEW_PROCESS):
                            # New Process started
                            self.logger.info("New child process started pid: %s" % pid.value)
                            print "winproc: new process, pid: %s" % pid.value
                        elif (msgid.value == winprocess.JOB_OBJECT_MSG_EXIT_PROCESS):
                            # One process exited normally
                            self.logger.info("Child Process %s has exited normally" % pid.value)
                            print "winproc: normal proc exit pid: %s" % pid.value
                        elif (msgid.value == winprocess.JOB_OBJECT_MSG_ABNORMAL_EXIT_PROCESS):
                            # One process existed abnormally
                            self.logger.info("Child Process %s has abnormally exited" % pid.value)
                            print "winproc: abnormal proc exit pid: %s" % pid.value
                        else:
                            # We don't care about anything else
                            print "winproc: caught else condition, keep polling"
                print "winproc: Exiting while loop, leaving thread"
                self._cleanup_job_and_io_port()
            
            def _wait(self, timeout=None):
                self.returncode = 0
                # TODO should there be a default timeout or is a timeout of None
                # waiting forever?  Do what popen generally does

                if self._job and self._procmgrthread.is_alive():
                    # Then we are managing with IO Completion Ports
                    # wait on a signal so we know when we have seen the last
                    # process come through.
                    print "Waiting for IO Port to let us know it is closed"
                    
                    # We use queues to synchronize between the thread and this 
                    # function because events just didn't have robust enough error
                    # handling on pre-2.7 versions
                    try:
                        item = self._process_events.get(timeout=timeout)
                        print "wait got item: %s" % item
                        if (item[self._procmgrthread.ident] == 'FINISHED'):
                            print "finished item"
                            self._process_events.task_done()
                    except Queue.Empty:
                        # Should we throw? 
                        self.logger.warn("IO Completion Port failed to signal process shutdown")
                    finally:
                        # Either way, let's try to get this code
                        self.returncode = winprocess.GetExitCodeProcess(self._handle)

                else:
                    # Not managing with job objects, so all we can reasonably do
                    # is call waitforsingleobject and hope for the best
                    if timeout is None:
                        timeout = -1
                    else:
                        # We need that timeout in milliseconds
                        timeout = timeout * 1000
                    rc = winprocess.WaitForSingleObject(self._handle, timeout)
                    if rc == winprocess.WAIT_TIMEOUT:
                        # TODO: Should this throw?
                        # I tend to think it should try to kill it directly at this point.
                        # But that might be reading too much into the mind of the user.
                        self.logger.warn("Timed out waiting for process to close, attempting TerminateProcess")
                        self.kill()
                    elif rc == winprocess.WAIT_OBJECT_0:
                        # We caught WAIT_OBJECT_0, which indicates all is well
                        self.logger.info("Single process terminated successfully")
                        self.returncode = winprocess.GetExitCodeProcess(self._handle)
                    else:
                        # An error occured we should probably throw
                        rc = winprocess.GetLastError()
                        raise WinError(rc)

                    return self.returncode

            def _cleanup_job_and_io_port(self):
                if self._job:
                    self._job.Close()
                    self._job = None
                if self._io_port:
                    self._io_port.Close()
                    self._io_port = None
                if self._procmgrthread:
                    self._procmgrthread = None
        elif sys.platform == "linux2" or (sys.platform in ('sunos5', 'solaris')):
            # Much of this linux and mac code remains unchanged from the killableprocess
            # implementation
            def _wait(self, timeout=timeout):
                def _linux_wait_callback(timeout):
                    try:
                        os.waitpid(self.pid, 0)
                    except OSError, e:
                        self.logger.warn("Encountered error waiting for pid to close: %s" e)
                    return self.returncode
                self.returncode = self._timed_wait_callback(_linux_wait_callback, timeout)
                return self.returncode
        elif sys.platform == "darwin":
            def _wait(self, timeout=timeout):
                def _mac_wait_callback(timeout):
                    try:
                        count = 0
                        print "macproc: timeout is: %s and self.kill_called: %s" % (timeout, self.kill_called)
                        # This function expects timeout in milliseconds
                        if timeout is None and self.kill_called:
                            # TODO: From killableprocess: "Have to set some kind of timeout
                            #       or else this could go on forever"
                            # I'm not sure why this hack exists, myself.
                            timeout = 10000
                        else:
                            timeout = timeout * 1000

                        if timeout is None:
                            # TODO: How do you break out of this loop
                            while 1:
                                print "macproc: CAUGHT FOREVER!"
                                os.killpg(self.pid, signal.SIG_DFL)

                        while ((count * 2) <= timeout):
                            os.killpg(self.pid, signal.SIG_DFL)
                            # count is increased by 500ms for every .5 of sleep
                            time.sleep(.5); count += 500
                    except exceptions.OSError:
                        print "Caught error during macproc"
                        return self.returncode
                    return self.returncode
                self.returncode = self._timed_wait_callback(_mac_wait_callback, timeout)
                return self.returncode
        else:
            # An unrecognized platform, we will call the base class for everything
            self.logger.warn("Unrecognized platform, process groups may not be managed properly")

            def _wait(self, timeout=timeout):
                self.returncode = subprocess.Popen.wait(self)
                return self.returncode
                
    def __init__(self,
                 cmd,
                 args=None,
                 cwd=None,
                 env = os.environ,
                 ignore_children = False,
                 logname = None,
                 **kwargs):
        """ Process Manager Class
            cmd = Command to run (defaults to None)
            args = array of arguments (defaults to None)
            cwd = working directory for cmd (defaults to None)
            env = environment to use for the process (defaults to os.environ)
            ignore_children = when True, causes system to ignore child processes,
                              defaults to False (which tracks child processes)
            logname = A logname for the python logger to use, if None (the default)
                      then the system python logger is used.
            kwargs = keyword args to pass directly into Popen
            
            NOTE: Child processes will be tracked by default.  If for any reason
            we are unable to track child processes and ignore_children is set to False,
            then we will fall back to only tracking the root process.  The fallback
            will be logged.
        """
        self.cmd = cmd
        self.args = args
        self.cwd = cwd
        self.env = env
        self.didTimeout = False
        self._output = []
        self._ignore_children = ignore_children
        self.keywordargs = **kwargs

        # The modules that use us can pass in a python logging module for us to
        # write to.  Failing that, we'll write to the system one.
        if (logname):
            self.logger = logging.getLogger(logname)
        else:
            self.logger = logging

    @property
    def timedOut(self):
        """True if the process has timed out."""
        return self.didTimeout

    @property
    def output(self):
        """Gets the output of the process."""
        return self._output

    def run(self):
        """Starts the process.  waitForFinish must be called to allow the
           process to complete.
        """
        self.didTimeout = False
        self.ouptut = []
        self.startTime = datetime.now()
        self.proc = self.Process([self.cmd] + self.args,
                                 stdout = subprocess.PIPE,
                                 stderr = subprocess.STDOUT,
                                 cwd=self.cwd,
                                 env = self.env,
                                 ignore_children = self._ignore_children,
                                 logger = self.logger,
                                 self.keywordargs)

    def kill(self):
        """
          Kills the managed process and if you created the process with
          'ignore_children=False' (the default) then it will also
          also kill all child processes spawned by it.
          If you specified 'ignore_children=True' when creating the process,
          only the root process will be killed.

          Note that this does not manage any state, save any output etc,
          it immediately kills the process.
        """
        return self.proc.kill()

    def readWithTimeout(self, f, timeout):
        """
          Try to read a line of output from the file object |f|.
          |f| must be a  pipe, like the |stdout| member of a subprocess.Popen
          object created with stdout=PIPE. If no output
          is received within |timeout| seconds, return a blank line.
          Returns a tuple (line, did_timeout), where |did_timeout| is True
          if the read timed out, and False otherwise.
          
          Calls a private member because this is a different function based on
          the OS
        """
        return self._readWithTimeout(f, timeout)

    def processOutputLine(self, line):
        """Called for each line of output that a process sends to stdout/stderr.
        """
        pass

    def onTimeout(self):
        """Called when a process times out."""
        pass

    def onFinish(self):
        """Called when a process finishes without a timeout."""
        pass

    def waitForFinish(self, timeout=None, outputTimeout=None, storeOutput=True, logfile=None):
        """Handle process output until the process terminates or times out.
    
           If timeout is not None, the process will be allowed to continue for
           that number of seconds before being killed.
       
           If outputTimeout is not None, the process will be allowed to continue
           for that number of seconds without producing any output before
           being killed.
       
           If storeOutput=True, the output produced by the process will be saved
           as self.output.
       
           If logfile is not None, the output produced by the process will be 
           appended to the given file.
        """
        self.didTimeout = False
        logsource = self.proc.stdout

        lineReadTimeout = None
        if timeout:
            lineReadTimeout = timeout - (datetime.now() - self.startTime).seconds
        elif outputTimeout:
            lineReadTimeout = outputTimeout

        if logfile is not None:
            log = open(logfile, 'a')

        (line, self.didTimeout) = self.readWithTimeout(logsource, lineReadTimeout)
        while line != "" and not self.didTimeout:
            if storeOutput:
                self._output.append(line.rstrip())
            if logfile is not None:
                log.write(line)
            self.processOutputLine(line)
            if timeout:
                lineReadTimeout = timeout - (datetime.now() - self.startTime).seconds
            (line, self.didTimeout) = self.readWithTimeout(logsource, lineReadTimeout)

        if logfile is not None:
            log.close()

        if self.didTimeout:
            self.proc.kill()
            self.onTimeout()
        else:
            self.onFinish()

        status = self.proc.wait()
        return status

    """
      Private Functions From here on down. Thar be dragons.
    """
    if sys.platform == 'win32':
        # Windows Specific private functions are defined in this block
        PeekNamedPipe = ctypes.windll.kernel32.PeekNamedPipe
        GetLastError = ctypes.windll.kernel32.GetLastError

        def _readWithTimeout(self, f, timeout):
            if timeout is None:
                # shortcut to allow callers to pass in "None" for no timeout.
                return (f.readline(), False)
            x = msvcrt.get_osfhandle(f.fileno())
            l = ctypes.c_long()
            done = time.time() + timeout
            while time.time() < done:
                if self.PeekNamedPipe(x, None, 0, None, ctypes.byref(l), None) == 0:
                    err = self.GetLastError()
                    if err == 38 or err == 109: # ERROR_HANDLE_EOF || ERROR_BROKEN_PIPE
                        return ('', False)
                    else:
                        log.error("readWithTimeout got error: %d", err)
                if l.value > 0:
                    # we're assuming that the output is line-buffered,
                    # which is not unreasonable
                    return (f.readline(), False)
                time.sleep(0.01)
            return ('', True)

    else:
        # Generic 
        def _readWithTimeout(self, f, timeout):
            try:
                (r, w, e) = select.select([f], [], [], timeout)
            except:
                # TODO: return a blank line?
                return ('', True)

            if len(r) == 0:
                return ('', True)
            return (f.readline(), False)
