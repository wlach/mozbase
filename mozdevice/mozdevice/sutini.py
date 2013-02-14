# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import ConfigParser
import StringIO
import os
import sys
import tempfile

from mozdevice.droid import DroidSUT
from mozdevice.devicemanager import DMError

USAGE = '%s <host>'
INI_PATH = '/data/data/com.mozilla.SUTAgentAndroid/files/SUTAgent.ini'
SCHEMA = { 'Registration Server': (('IPAddr', None),
                                   ('PORT', '28001'),
                                   ('HARDWARE', None),
                                   ('POOL', None)) }


def get_cfg(d):
    cfg = ConfigParser.RawConfigParser()
    try:
        cfg.readfp(StringIO.StringIO(d.catFile(INI_PATH)), 'SUTAgent.ini')
    except DMError:
        # assume this is due to a missing file...
        pass
    return cfg


def put_cfg(d, cfg):
    print 'Writing modified SUTAgent.ini...'
    t = tempfile.NamedTemporaryFile(delete=False)
    cfg.write(t)
    t.close()
    try:
        d.pushFile(t.name, INI_PATH)
    except DMError, e:
        print e
    else:
        print 'Done.'
    finally:
        os.unlink(t.name)


def set_opt(cfg, s, o, dflt):
    prompt = '  %s' % o
    try:
        curval = cfg.get(s, o)
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
        curval = ''
    if curval:
        dflt = curval
    if dflt:
        prompt += ' [%s]' % dflt
    prompt += ': '
    newval = raw_input(prompt)
    if not newval:
        newval = dflt
    if newval == curval:
        return False
    cfg.set(s, o, newval)
    return True


def main():
    try:
        host = sys.argv[1]
    except IndexError:
        print USAGE % sys.argv[0]
        sys.exit(1)
    try:
        d = DroidSUT(host, retryLimit=1)
    except DMError, e:
        print e
        sys.exit(1)
    cfg = get_cfg(d)
    if not cfg.sections():
        print 'Empty or missing ini file.'
    changed_vals = False
    for sect, opts in SCHEMA.iteritems():
        if not cfg.has_section(sect):
            cfg.add_section(sect)
        print '%s settings:' % sect
        for opt, dflt in opts:
            changed_vals |= set_opt(cfg, sect, opt, dflt)
        print
    if changed_vals:
        put_cfg(d, cfg)
    else:
        print 'No changes.'


if __name__ == '__main__':
    main()