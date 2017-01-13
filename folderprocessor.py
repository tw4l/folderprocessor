#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Creates Archivematica-ready SIPs from folders on local filesystem, external media,
and/or network shares, as well as a pre-populated description spreadsheet.

User inputs single directory. Default behavior is to create a SIP of this source. 
To create SIPs for each immediate child directory instead, pass the "-c" or 
"--children" argument.

Will create metadata/checksum.md5 file saved in metadata directory by default. 
To create bags instead, pass the "-b" or "--bagfiles" argument.

To have Brunnhilde also complete a PII scan using bulk_extractor, pass the
"-p" or "-piiscan" argument.

Python 2.7

MIT License
(c) Tim Walsh 2016
http://bitarchivist.net
"""

from __future__ import print_function
import argparse
import csv
import datetime
import itertools
import math
import os
import shutil
import subprocess
import sys
from time import localtime, strftime

def get_immediate_subdirectories(a_dir):
    return [name for name in os.listdir(a_dir)
            if os.path.isdir(os.path.join(a_dir, name))]

def logandprint(message):
    log.write('\n' + (strftime("%H:%M:%S %b %d, %Y - ", localtime())) + message)
    print(message)

def convert_size(size):
    # convert size to human-readable form
    if size == 0:
        return '0 bytes'
    size_name = ("bytes", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size,1024)))
    p = math.pow(1024,i)
    s = round(size/p)
    s = str(s)
    s = s.replace('.0', '')
    return '%s %s' % (s,size_name[i])

def create_sip(folder):
    current_dir = os.path.abspath(os.path.join(args.source, folder))
    basename = os.path.basename(folder)

    # record foldername
    logandprint('PROCESSING NEW DIRECTORY: %s' % folder)

    # create folders for SIP
    logandprint('Creating SIP directory structure for %s' % folder)

    sip_dir = os.path.join(sips, basename)
    object_dir = os.path.join(sip_dir, 'objects')
    metadata_dir = os.path.join(sip_dir, 'metadata')
    subdoc_dir = os.path.join(metadata_dir, 'submissionDocumentation')

    log.write('\n' + (strftime("%H:%M:%S %b %d, %Y - ", localtime())) + 'Making SIP directory ' + sip_dir)
    for newfolder in sip_dir, object_dir, metadata_dir:
        os.makedirs(newfolder)

    # copy files (rsync, don't copy Thumbs.db or .DS_Store)
    subprocess.call("rsync -avc --stats '%s' '%s'" % (current_dir, object_dir), shell=True)
    logandprint('Files successfully rsynced to %s' % sip_dir)

    # write checksums
    if args.bagfiles == True: # bag entire SIP
        subprocess.call("bagit.py --processes 4 '%s'" % sip_dir, shell=True)
        logandprint('%s successfully bagged.' % sip_dir)
    else: # write metadata/checksum.md5
        subprocess.call("cd '%s' && md5deep -rl ../objects > checksum.md5" % metadata_dir, shell=True)
        logandprint('Checksums for %s/objects/ successfully generated by md5deep and written to checksum.md5.' % sip_dir)

    # modify file permissions
    subprocess.call("sudo find '%s' -type d -exec chmod 755 {} \;" % sip_dir, shell=True)
    subprocess.call("sudo find '%s' -type f -exec chmod 644 {} \;" % sip_dir, shell=True)
    logandprint('File permissions rewritten.')

    # run Brunnhilde amd write to submissionDocumentation directory
    if args.bagfiles == True:
        files_abs = os.path.abspath(os.path.join(sip_dir, 'data', 'objects'))
        subdoc_dir = os.path.abspath(os.path.join(sip_dir, 'data', 'metadata', 'submissionDocumentation'))
    else:
        files_abs = os.path.abspath(object_dir)
    
    logandprint('Running Brunnhilde on %s' % sip_dir)
    if args.piiscan == True: # brunnhilde with bulk_extractor
        subprocess.call("brunnhilde.py -zbw '%s' '%s' '%s_brunnhilde'" % (files_abs, subdoc_dir, basename), shell=True)
    else: # brunnhilde without bulk_extractor
        subprocess.call("brunnhilde.py -zw '%s' '%s' '%s_brunnhilde'" % (files_abs, subdoc_dir, basename), shell=True)
    logandprint('Brunnhilde report written. Finished processing %s. Outputs written to %s.' % (folder, destination))

def create_spreadsheet():
    # process each SIP
    for item in os.listdir(sips):
        current = os.path.join(sips, item)
        # test if entry if directory
        if os.path.isdir(current):
            
            # gather info from files
            if args.bagfiles == True:
                objects = os.path.abspath(os.path.join(current, 'data', 'objects'))
            else:
                objects = os.path.abspath(os.path.join(current, 'objects'))

            number_files = 0
            total_bytes = 0
            mdates = []

            for root, directories, filenames in os.walk(objects):
                for filename in filenames:
                    # add to file count
                    number_files += 1
                    # add number of bytes to total
                    filepath = os.path.join(root, filename)
                    total_bytes += os.path.getsize(filepath)
                    # add modified date to list
                    modified = os.path.getmtime(filepath)
                    modified_date = str(datetime.datetime.fromtimestamp(modified))
                    mdates.append(modified_date)

            # build extent statement
            size_readable = convert_size(total_bytes)
            if number_files == 1:
                extent = "1 digital file (%s)" % size_readable
            elif number_files == 0:
                extent = "EMPTY"
            else:
                extent = "%d digital files (%s)" % (number_files, size_readable)

            # build date statement
            if mdates:
                date_earliest = min(mdates)[:10]
                date_latest = max(mdates)[:10]
            else:
                date_earliest = 'N/A'
                date_latest = 'N/A'
            if date_earliest == date_latest:
                date_statement = '%s' % date_earliest[:4]
            else:
                date_statement = '%s - %s' % (date_earliest[:4], date_latest[:4])

            # gather info from burnnhilde & write scope and content note
            if extent == 'EMPTY':
                scopecontent = ''
            else:
                fileformats = []
                if args.bagfiles == True:
                    fileformat_csv = os.path.join(current, 'data', 'metadata', 'submissionDocumentation', '%s_brunnhilde' % os.path.basename(current), 'csv_reports', 'formats.csv')
                else:
                    fileformat_csv = os.path.join(current, 'metadata', 'submissionDocumentation', '%s_brunnhilde' % os.path.basename(current), 'csv_reports', 'formats.csv')
                with open(fileformat_csv, 'r') as f:
                    reader = csv.reader(f)
                    reader.next()
                    for row in itertools.islice(reader, 5):
                        fileformats.append(row[0])
                fileformats = [element or 'Unidentified' for element in fileformats] # replace empty elements with 'Unidentified'
                formatlist = ', '.join(fileformats) # format list of top file formats as human-readable
                
                # create scope and content note
                scopecontent = 'Files from directory titled "%s". Most common file formats: %s' % (os.path.basename(current), formatlist)

            # write csv row
            writer.writerow(['', item, '', '', date_statement, date_earliest, date_latest, 'File', extent, 
                scopecontent, '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
            
            logandprint('Described %s successfully.' % current)

    logandprint('All SIPs described in spreadsheet. Process complete.')

# MAIN FLOW

# parse arguments
parser = argparse.ArgumentParser()
parser.add_argument("-b", "--bagfiles", help="Bag files instead of writing checksum.md5", action="store_true")
parser.add_argument("-c", "--children", help='Create SIPs of each immediate child directory', action="store_true")
parser.add_argument("-p", "--piiscan", help="Run bulk_extractor in Brunnhilde scan", action="store_true")
parser.add_argument("source", help="Path to source directory")
parser.add_argument("destination", help="Path to save SIPs")
args = parser.parse_args()

destination = args.destination

# create output directories
if not os.path.exists(destination):
    os.makedirs(destination)

sips = os.path.join(destination, 'SIPs')
os.makedirs(sips)

# open log file
log_file = os.path.join(destination, 'folderprocessor-log.txt')
try:
    log = open(log_file, 'w')   # open the log file
    logandprint('Log file started.')
    logandprint('Source of folders: %s' % args.source)
except:
    sys.exit('There was an error creating the log file.')

# open description spreadsheet
try:
    spreadsheet = open(os.path.join(destination,'description.csv'), 'w')
    writer = csv.writer(spreadsheet, quoting=csv.QUOTE_NONNUMERIC)
    header_list = ['Parent ID', 'Identifier', 'Title', 'Archive Creator', 'Date expression', 'Date start', 'Date end', 
        'Level of description', 'Extent and medium', 'Scope and content', 'Arrangement (optional)', 'Accession number', 
        'Appraisal, destruction, and scheduling information (optional)', 'Name access points (optional)', 
        'Geographic access points (optional)', 'Conditions governing access (optional)', 'Conditions governing reproduction (optional)', 
        'Language of material (optional)', 'Physical characteristics & technical requirements affecting use (optional)', 
        'Finding aids (optional)', 'Related units of description (optional)', 'Archival history (optional)', 
        'Immediate source of acquisition or transfer (optional)', "Archivists' note (optional)", 'General note (optional)', 
        'Description status']
    writer.writerow(header_list)
    logandprint('Description spreadsheet created.')
except:
    sys.exit('There was an error creating the processing spreadsheet.')

# process source or its immediate children
if args.children == True:
    # get subdirectories
    subdirs = []
    subdirs = get_immediate_subdirectories(args.source)
    for subdir in subdirs:
        create_sip(subdir)
else:
    create_sip(args.source)

# write description spreadsheet
create_spreadsheet()

# close files
spreadsheet.close()
log.close()

