import json
import os
import shutil
import tarfile
import time
import traceback
import zipfile
from datetime import datetime
from threading import RLock
import re
from couchpotato.core.event import addEvent, fireEvent, fireEventAsync
from couchpotato.core.helpers.variable import removePyc
from couchpotato.core.logger import CPLog
from couchpotato.core.helpers.encoding import sp
from couchpotato.core.plugins.base import Plugin
from couchpotato.environment import Env
from dateutil.parser import parse
from git.repository import LocalRepository
import version
from six.moves import filter

log = CPLog(__name__)

class T411Updater(Plugin):

    repo_user = 'cocazoulou'
    repo_name = 'couchpotato.provider.t411'
    branch = 'Auto-updater'

    version = None
    update_failed = False
    update_version = None
    last_check = 0

    def doUpdate(self):
        pass

    def info(self):

        current_version = self.getVersion()

        return {
            'last_check': self.last_check,
            'update_version': self.update_version,
            'version': current_version,
            'repo_name': '%s/%s' % (self.repo_user, self.repo_name),
            'branch': current_version.get('branch', self.branch),
        }

    def getVersion(self):
        pass

    def check(self):
        pass
    
class ST411Updater(T411Updater):

    def __init__(self):

        # Create version file in cache
        self.version_file = os.path.join(Env.get('cache_dir'), 'version.t411')
        if not os.path.isfile(self.version_file):
            self.createFile(self.version_file, json.dumps(self.latestCommit()))

    def doUpdate(self):
        try:
            url = 'https://codeload.github.com/%s/%s/zip/%s' % (self.repo_user, self.repo_name, self.branch)
            
            destination = os.path.join(Env.get('cache_dir'), self.update_version.get('hash')) + '.zip'

            extracted_path = os.path.join(Env.get('cache_dir'), 'temp_updater.t411')
            destination = fireEvent('file.download', url = url, dest = destination, single = True)
            
            # Cleanup leftover from last time
            if os.path.isdir(extracted_path):
                self.removeDir(extracted_path)
            self.makeDir(extracted_path)

            # Extract
            zip_file = zipfile.ZipFile(destination)
            zip_file.extractall(extracted_path)
            zip_file.close()

            os.remove(destination)
            
            if self.replaceWith(os.path.join(extracted_path, os.listdir(extracted_path)[0], 't411')):
                self.removeDir(extracted_path)

                # Write update version to file
                self.createFile(self.version_file, json.dumps(self.update_version))

                return True
        except:
            log.error('Failed updating: %s', traceback.format_exc())

        self.update_failed = True
        return False

    def replaceWith(self, path):
        path = sp(path)
        plugins_folder = os.path.dirname(os.path.abspath(__file__))
        

        # Get list of files we want to overwrite
        removePyc(plugins_folder)
        existing_files = []
        for root, subfiles, filenames in os.walk(plugins_folder):
            for filename in filenames:
                existing_files.append(os.path.join(root, filename))

        for root, subfiles, filenames in os.walk(path):
            for filename in filenames:
                fromfile = os.path.join(root, filename)
                tofile = os.path.join(plugins_folder, fromfile.replace(path + os.path.sep, ''))

                if not Env.get('dev'):
                    try:
                        if os.path.isfile(tofile):
                            os.remove(tofile)

                        dirname = os.path.dirname(tofile)
                        if not os.path.isdir(dirname):
                            self.makeDir(dirname)

                        shutil.move(fromfile, tofile)
                        try:
                            existing_files.remove(tofile)
                        except ValueError:
                            pass
                    except:
                        log.error('Failed overwriting file "%s": %s', (tofile, traceback.format_exc()))
                        return False

        for still_exists in existing_files:

            try:
                os.remove(still_exists)
            except:
                log.error('Failed removing non-used file: %s', traceback.format_exc())

        return True

    def removeDir(self, path):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
        except OSError as inst:
            os.chmod(inst.filename, 0o777)
            self.removeDir(path)

    def getVersion(self):

        if not self.version:
            try:
                f = open(self.version_file, 'r')
                output = json.loads(f.read())
                f.close()

                log.debug('Source version output: %s', output)
                self.version = output
                self.version['type'] = 'source'
                self.version['repr'] = 'source:(%s:%s % s) %s (%s)' % (self.repo_user, self.repo_name, self.branch, output.get('hash', '')[:8], datetime.fromtimestamp(output.get('date', 0)))
            except Exception as e:
                log.error('Failed using source updater. %s', e)
                return {}

        return self.version

    def check(self):

        current_version = self.getVersion()

        try:
            latest = self.latestCommit()
            
            log.debug('Current hash: %s' % current_version.get('hash'))
            log.debug('New hash: %s' % latest.get('hash'))
            
            if latest.get('hash') != current_version.get('hash') and latest.get('date') >= current_version.get('date'):
                self.update_version = latest

            self.last_check = time.time()
        except:
            log.error('Failed updating via source: %s', traceback.format_exc())

        return self.update_version is not None

    def latestCommit(self):
        try:
            url = 'https://api.github.com/repos/%s/%s/commits?per_page=1&sha=%s' % (self.repo_user, self.repo_name, self.branch)
            data = self.getCache('github.commit', url = url)
            commit = json.loads(data)[0]

            return {
                'hash': commit['sha'],
                'date': int(time.mktime(parse(commit['commit']['committer']['date']).timetuple())),
            }
        except:
            log.error('Failed getting latest request from github: %s', traceback.format_exc())

        return {}