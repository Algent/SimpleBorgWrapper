#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import ConfigParser
import logging
import shlex
import smtplib
import re
from logging.handlers import TimedRotatingFileHandler
from time import strftime, time, gmtime
from subprocess import Popen, PIPE
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate


def main():
    # ### START MAIN ### #

    # Check for missing files
    if not os.path.isfile('SimpleBorgWrapper.ini'):
        quit('ERROR: Could not find SimpleBorgWrapper.ini')
    if not os.path.isfile('SimpleBorgWrapper-report.html'):
        quit('ERROR: Could not find borg_report_tmpl.html')

    # Read fonfiguration file
    config = ConfigParser.ConfigParser()
    config.read('SimpleBorgWrapper.ini')
    borg_bin_path = config.get('Borg', 'borg_bin_path')
    borg_repository = config.get('Borg', 'borg_repository')
    borg_passphrase = config.get('Borg', 'borg_passphrase')
    borg_prefix = config.get('Borg', 'borg_prefix')
    borg_paths_to_archive = config.get('Borg', 'borg_paths_to_archive')
    borg_create_args = config.get('Borg', 'borg_create_args')
    borg_check_args = config.get('Borg', 'borg_check_args')
    borg_prune_args = config.get('Borg', 'borg_prune_args')
    log_dir = config.get('Logs', 'log_dir')
    log_filename = config.get('Logs', 'log_filename')
    report_from = config.get('Reports', 'report_from')
    report_to = config.get('Reports', 'report_to')
    report_subject = config.get('Reports', 'report_subject')
    report_smtp = config.get('Reports', 'report_smtp')
    server_name = config.get('Misc', 'server_name')

    # Starting logging
    init_logger(log_dir + log_filename)

    # ## BEGIN BACKUP ##
    time_started_nice = strftime('%A %d %B %Y %H:%M:%S')
    time_started = strftime('%Y-%m-%d %H:%M:%S')
    stopwatch = time()
    log_info('Starting backup of ' + server_name)
    os.environ['BORG_PASSPHRASE'] = borg_passphrase
    create_rc = borg_create(borg_bin_path, borg_repository, borg_prefix, borg_create_args, borg_paths_to_archive)
    check_rc = borg_check(borg_bin_path, borg_repository, borg_check_args)
    prune_rc = borg_prune(borg_bin_path, borg_repository, borg_prefix, borg_prune_args)
    list_rc = borg_list(borg_bin_path, borg_repository)
    os.environ['BORG_PASSPHRASE'] = ""
    log_info('End of backup with Status: ' + get_rc_result(wrapper_rc))
    log_info('Sending report...')
    time_ended = strftime('%Y-%m-%d %H:%M:%S')
    time_elapsed = round(time() - stopwatch, 2)
    # ## END BACKUP ##

    # ## BEGIN REPORT ##
    # TODO Add option to disable reports
    # TODO Add fulltext
    with open('SimpleBorgWrapper-report.html', 'r') as report_body_template:
        report_body = report_body_template.read()
    report_body = report_body.replace('%%SRVNAME%%', server_name)
    report_body = report_body.replace('%%NICETIME%%', time_started_nice, 1)
    report_body = report_body.replace('%%STARTTIME%%', time_started, 1)
    report_body = report_body.replace('%%ENDTIME%%', time_ended, 1)
    report_body = report_body.replace('%%DURATION%%', strftime('%H:%M:%S', gmtime(time_elapsed)), 1)
    report_body = report_body.replace('%%ENDRESULT%%', get_rc_result(wrapper_rc), 2)
    report_body = report_body.replace('%%BCREATE%%', get_rc_result(create_rc), 2)
    report_body = report_body.replace('%%BCHECK%%', get_rc_result(check_rc), 2)
    report_body = report_body.replace('%%BPRUNE%%', get_rc_result(prune_rc), 2)
    report_body = report_body.replace('%%BLIST%%', get_rc_result(list_rc), 2)
    # TODO Improve log formatting: Columns in output are a bit borked.
    report_body = report_body.replace('%%FULL_LOG%%', live_log.replace('\n', '\n<br/>').replace(' ', '&nbsp;'))
    report_from = report_from.replace('%%SRVNAME%%', server_name, 1)
    report_subject = report_subject.replace('%%ENDRESULT%%', get_rc_result(wrapper_rc), 1)
    report_subject = report_subject.replace('%%SRVNAME%%', server_name, 1)
    send_report(report_from, shlex.split(report_to.replace(', ', ' ')), report_subject, report_body, report_smtp)
    # ## END REPORT ##

    # ### END MAIN ### #
    exit(0)


def borg_create(borg_bin, repo, prefix, args, to_archive):
    log_info('START - Borg Create')
    archive = ' ' + repo + '::' + prefix + '-' + strftime('%Y-%m-%d_%H-%M') + ' '
    cmd = borg_bin + ' create ' + args + archive + to_archive
    create_rc, create_stdout, create_stderr = run_cmd_get_output(cmd)
    log_info('OUTPUT - Borg Create:\n' + create_stderr)
    log_info('STATUS - ' + verify_rc(create_rc) + " - [rc " + str(create_rc) + "]")
    log_info('END - Borg Create')
    return create_rc


def borg_check(borg_bin, repo, args):
    log_info('START - Borg Check')
    cmd = borg_bin + ' check ' + args + ' ' + repo
    check_rc, check_stdout, check_stderr = run_cmd_get_output(cmd)
    check_stderr = re.sub('Remote: Checking segments \d{1,3}.\d%\r', '', check_stderr)
    check_stderr = re.sub('Remote: {25}\r', 'Remote: Checking segments...\n', check_stderr)
    log_info('OUTPUT - Borg Check:\n' + check_stderr)
    log_info('STATUS - ' + verify_rc(check_rc) + " - [rc " + str(check_rc) + "]")
    log_info('END - Borg Check')
    return check_rc


def borg_prune(borg_bin, repo, prefix, args):
    log_info('START - Borg Prune')
    args += ' -P ' + prefix + ' '
    cmd = borg_bin + ' prune ' + args + repo
    prune_rc, prune_stdout, prune_stderr = run_cmd_get_output(cmd)
    log_info('OUTPUT - Borg Prune:\n' + prune_stderr)
    log_info('STATUS - ' + verify_rc(prune_rc) + " - [rc " + str(prune_rc) + "]")
    log_info('END - Borg Prune')
    return prune_rc


def borg_list(borg_bin, repo):
    log_info('START - Borg List')
    cmd = borg_bin + ' list ' + repo
    list_rc, list_stdout, list_stderr = run_cmd_get_output(cmd)
    log_info('OUTPUT - Borg List:\n' + list_stdout)
    log_info('STATUS - ' + verify_rc(list_rc) + " - [rc " + str(list_rc) + "]")
    log_info('END - Borg List')
    return list_rc


def init_logger(path):
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s')
    file_handler = TimedRotatingFileHandler(filename=path, when='H', interval=12, backupCount=10)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    logger.addHandler(stream_handler)


def log_info(text):
    global live_log
    logger.info(text)
    live_log += strftime('[%Y-%m-%d %H:%M:%S] ') + text + '\n'


def run_cmd_get_output(cmd):
    log_info('EXEC - ' + cmd)
    args = shlex.split(cmd)
    proc = Popen(args, stdout=PIPE, stderr=PIPE)
    stdout, stderr = proc.communicate()
    exitcode = proc.returncode
    return exitcode, stdout, stderr


def verify_rc(rc):
    global wrapper_rc
    if rc == 0:
        return 'Success'
    elif rc == 1:
        if wrapper_rc != 2:
            wrapper_rc = 1
        return 'Warning'
    else:
        wrapper_rc = 2
        return 'Error'


def get_rc_result(rc):
    if rc == 0:
        return 'Success'
    elif rc == 1:
        return 'Warning'
    else:
        return 'Error'


def send_report(msg_from, msg_to, msg_subject, msg_body, msg_smtp):
    msg = MIMEMultipart('alternative')
    msg['From'] = msg_from
    msg['To'] = msg_to
    msg['Subject'] = msg_subject
    msg['Date'] = formatdate(localtime=True)
    msg_body = MIMEText(msg_body, 'html')
    msg.attach(msg_body)
    s = smtplib.SMTP(msg_smtp)
    s.sendmail(msg_from, msg_to, msg.as_string())
    s.quit()


if __name__ == '__main__':
    logger = logging.getLogger('borg_wrapper')
    live_log = ''
    wrapper_rc = 0
    main()
